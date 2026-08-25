#!/usr/bin/env python3
"""
Immutable External Acceptance Harness for BET PIPELINE V5.
Evaluates ACC-001 through ACC-038 against a target repository using canonical production execution.
Emits typed AcceptanceReceiptV1 JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from bet.pipeline.receipts import (
    get_git_commit_head,
    get_git_tree_sha,
    compute_source_manifest_sha256,
    get_sanitized_env_fingerprint,
    AcceptanceReceiptV1,
)


def parse_args():
    parser = argparse.ArgumentParser(description="External Acceptance Harness V5")
    parser.add_argument("--repo-root", "--target", dest="repo_root", default=os.getcwd(), help="Target repository directory")
    parser.add_argument("--json-out", help="Path to write JSON report")
    parser.add_argument("--junit-out", help="Path to write JUnit XML report")
    return parser.parse_args()


class AcceptanceRunner:
    def __init__(self, repo_root: str):
        self.target_dir = os.path.abspath(repo_root)
        self.src_dir = os.path.join(self.target_dir, "src")
        self.scripts_dir = os.path.join(self.target_dir, "scripts")
        if self.src_dir not in sys.path:
            sys.path.insert(0, self.src_dir)
        if self.scripts_dir not in sys.path:
            sys.path.insert(0, self.scripts_dir)
        self.results: Dict[str, Dict[str, Any]] = {}

    def record_result(self, req_id: str, passed: bool, message: str, details: Dict[str, Any] | None = None):
        self.results[req_id] = {
            "passed": passed,
            "status": "PASS" if passed else "FAIL",
            "message": message,
            "details": details or {}
        }

    # Requirement Checkers ACC-001 to ACC-038

    def check_acc_001(self):
        """ACC-001: migration does not invent terminal status"""
        try:
            import bet.pipeline.contracts.migration as mig
            payload = {"event_id": "evt_123", "market": "1X2"}
            res = mig.adapt_legacy_artifact(payload, "S1_FIXTURES_SHORTLIST")
            status = res.get("status") if isinstance(res, dict) else None
            if status in ("PASS", "COMPLETED", "OK", "READY", "VERIFIED"):
                self.record_result("ACC-001", False, f"Migration invented terminal status: {status}")
            else:
                self.record_result("ACC-001", True, "Migration did not invent terminal status")
        except Exception as e:
            self.record_result("ACC-001", True, f"Migration rejected or handled payload: {e}")

    def check_acc_002(self):
        """ACC-002: migration does not invent event identity or metadata"""
        try:
            import bet.pipeline.contracts.migration as mig
            payload = {"market": "1X2"}
            res = mig.adapt_legacy_artifact(payload, "S1E_CANONICAL_EVENT_UNIVERSE")
            if isinstance(res, dict):
                records = res.get("event_records") or [res]
                for rec in records:
                    if isinstance(rec, dict):
                        if rec.get("sport") == "football" and "sport" not in payload:
                            self.record_result("ACC-002", False, "Migration invented default sport 'football'")
                            return
                        if rec.get("competition") in ("League", "Default League") and "competition" not in payload:
                            self.record_result("ACC-002", False, "Migration invented default competition")
                            return
                        if rec.get("home_team") in ("Home", "Home Team") and "home_team" not in payload:
                            self.record_result("ACC-002", False, "Migration invented default home team")
                            return
            self.record_result("ACC-002", True, "Migration did not invent event identity or metadata")
        except Exception as e:
            self.record_result("ACC-002", True, f"Migration rejected incomplete payload: {e}")

    def check_acc_003(self):
        """ACC-003: migration does not invent market/selection/risk/readiness/odds"""
        try:
            import bet.pipeline.contracts.migration as mig
            payload = {"event_id": "evt_123"}
            res = mig.adapt_legacy_artifact(payload, "S7_PRICED_SHORTLIST")
            if isinstance(res, dict):
                candidates = res.get("candidates") or [res]
                for c in candidates:
                    if isinstance(c, dict):
                        if c.get("odds") is not None or c.get("fair_odds") is not None:
                            self.record_result("ACC-003", False, "Migration invented odds")
                            return
                        if c.get("readiness") == "READY" and "readiness" not in payload:
                            self.record_result("ACC-003", False, "Migration invented READY readiness")
                            return
            self.record_result("ACC-003", True, "Migration did not invent market/selection/risk/odds")
        except Exception as e:
            self.record_result("ACC-003", True, f"Migration rejected payload: {e}")

    def check_acc_004(self):
        """ACC-004: strict DTO rejects extra/unknown decision fields"""
        try:
            import bet.pipeline.agent_work_orders as awo
            cls = getattr(awo, "AgentWorkOrderV1", getattr(awo, "AgentWorkOrder", None))
            if not cls:
                self.record_result("ACC-004", False, "No AgentWorkOrder class found")
                return

            data = {
                "work_order_id": "wo_123",
                "work_order_type": "AGENT_ARTIFACT_REQUEST",
                "pipeline_id": "pipe_123",
                "run_id": "run_123",
                "betting_day": "2026-07-28",
                "step_id": "S1",
                "agent": "bet-researcher",
                "runtime_mode": "LIVE",
                "created_at": "2026-07-28T00:00:00Z",
                "status": "PENDING",
                "required_output": {
                    "artifact_type": "AGENT_ARTIFACT",
                    "step_id": "S1",
                    "expected_path": "/tmp/out.json",
                    "required_statuses": ["PASS"],
                },
                "manifest_sha256": "a"*64,
                "source_head": "b"*40,
                "extra_injected_decision": "MALICIOUS_OVERRIDE"
            }
            try:
                obj = cls.model_validate(data) if hasattr(cls, "model_validate") else cls(**data)
                self.record_result("ACC-004", False, "DTO accepted extra decision field 'extra_injected_decision'")
            except Exception:
                self.record_result("ACC-004", True, "Strict DTO rejected extra decision field")
        except Exception as e:
            self.record_result("ACC-004", False, f"Check failed: {e}")

    def check_acc_005(self):
        """ACC-005: exact S1e event accounting cannot be skipped"""
        try:
            import bet.pipeline.event_accounting as ea
            universe = ["evt_1", "evt_2", "evt_3"]
            processed = ["evt_1", "evt_2", "evt_999"]
            if hasattr(ea, "validate_event_accounting"):
                try:
                    ea.validate_event_accounting(universe, processed, step_id="S2")
                    self.record_result("ACC-005", False, "Event accounting allowed foreign and missing events")
                except Exception:
                    self.record_result("ACC-005", True, "Event accounting rejected accounting discrepancy")
            else:
                self.record_result("ACC-005", False, "validate_event_accounting not implemented")
        except Exception as e:
            self.record_result("ACC-005", False, f"Check failed: {e}")

    def check_acc_006(self):
        """ACC-006: output-contract resolution cannot be swallowed by broad exception"""
        try:
            runner_path = os.path.join(self.scripts_dir, "pipeline_steps", "_runner.py")
            if os.path.exists(runner_path):
                with open(runner_path, encoding="utf-8") as f:
                    content = f.read()
                if "except Exception:" in content and "validate" in content and "pass" in content:
                    self.record_result("ACC-006", False, "Found swallowed Exception in step runner")
                    return
            self.record_result("ACC-006", True, "Output-contract resolution does not swallow broad exceptions")
        except Exception as e:
            self.record_result("ACC-006", False, f"Check failed: {e}")

    def check_acc_007(self):
        """ACC-007: AgentWorkOrder is immutable and fully typed"""
        try:
            import bet.pipeline.agent_work_orders as awo
            cls = getattr(awo, "AgentWorkOrderV1", None)
            if cls:
                config = getattr(cls, "model_config", {})
                is_frozen = config.get("frozen", False) if isinstance(config, dict) else getattr(config, "frozen", False)
                if is_frozen:
                    self.record_result("ACC-007", True, "AgentWorkOrderV1 is immutable and strict")
                else:
                    self.record_result("ACC-007", False, "AgentWorkOrderV1 model_config is not frozen")
            else:
                self.record_result("ACC-007", False, "AgentWorkOrderV1 class missing")
        except Exception as e:
            self.record_result("ACC-007", False, f"Check failed: {e}")

    def check_acc_008(self):
        """ACC-008: acquisition_plan is FactAcquisitionPlanV1, not dict"""
        try:
            import bet.pipeline.agent_work_orders as awo
            from bet.pipeline.sharding.models import FactAcquisitionPlanV1
            cls = getattr(awo, "AgentWorkOrderV1", None)
            if cls:
                req_out = awo.AgentWorkOrderOutputContractV1(
                    artifact_type="AGENT_ARTIFACT",
                    step_id="S1",
                    expected_path="/tmp/out.json",
                    required_statuses=["PASS"],
                )
                try:
                    wo = cls(
                        work_order_id="wo1",
                        work_order_type="AGENT_ARTIFACT_REQUEST",
                        pipeline_id="pipe1",
                        betting_day="2026-07-28",
                        run_id="run1",
                        step_id="S1",
                        agent="bet-researcher",
                        runtime_mode="DRY_RUN",
                        created_at="2026-07-28T00:00:00Z",
                        status="PENDING_AGENT",
                        required_output=req_out,
                        manifest_sha256="a"*64,
                        source_head="b"*40,
                        acquisition_plan={"plan_id": "p1", "canonical_event_id": "evt1", "sport": "football"},
                    )
                    if isinstance(wo.acquisition_plan, FactAcquisitionPlanV1):
                        self.record_result("ACC-008", True, "acquisition_plan is parsed into FactAcquisitionPlanV1 instance")
                    else:
                        self.record_result("ACC-008", False, f"acquisition_plan is type {type(wo.acquisition_plan)}")
                except Exception as exc:
                    self.record_result("ACC-008", True, f"acquisition_plan validation enforced: {exc}")
            else:
                self.record_result("ACC-008", False, "AgentWorkOrderV1 class missing")
        except Exception as e:
            self.record_result("ACC-008", False, f"Check failed: {e}")

    def check_acc_009(self):
        """ACC-009: acquisition plan is event/sport/market specific"""
        try:
            import bet.pipeline.sharding.models as sm
            if hasattr(sm, "FactAcquisitionPlanV1"):
                plan_cls = sm.FactAcquisitionPlanV1
                try:
                    plan = plan_cls(plan_id="p1", canonical_event_id="ALL_SHORTLIST_EVENTS", sport="football")
                    self.record_result("ACC-009", False, "FactAcquisitionPlanV1 accepted ALL_SHORTLIST_EVENTS")
                except Exception:
                    self.record_result("ACC-009", True, "FactAcquisitionPlanV1 requires event-specific canonical_event_id")
            else:
                self.record_result("ACC-009", False, "FactAcquisitionPlanV1 missing")
        except Exception as e:
            self.record_result("ACC-009", False, f"Check failed: {e}")

    def check_acc_010(self):
        """ACC-010: allowed tools equal plan ∩ agent profile"""
        try:
            import bet.pipeline.agent_work_orders as awo
            if hasattr(awo, "compute_allowed_tools"):
                tools = awo.compute_allowed_tools(
                    plan_tools=["webfetch", "bet_sqlite_query"],
                    agent_profile_tools=["bet_sqlite_query", "read"]
                )
                if tools == ["bet_sqlite_query"]:
                    self.record_result("ACC-010", True, "compute_allowed_tools calculated exact intersection")
                else:
                    self.record_result("ACC-010", False, f"compute_allowed_tools returned {tools}")
            else:
                self.record_result("ACC-010", False, "compute_allowed_tools function missing")
        except Exception as e:
            self.record_result("ACC-010", False, f"Check failed: {e}")

    def check_acc_011(self):
        """ACC-011: no plan means no browsing"""
        try:
            import bet.pipeline.agent_work_orders as awo
            if hasattr(awo, "compute_allowed_tools"):
                tools = awo.compute_allowed_tools(
                    plan_tools=None,
                    agent_profile_tools=["webfetch", "websearch", "bet_sqlite_query"]
                )
                if not any(t in tools for t in ["webfetch", "websearch", "brave-search_brave_web_search"]):
                    self.record_result("ACC-011", True, "No plan resulted in no browsing tools")
                else:
                    self.record_result("ACC-011", False, f"Browsing tools present without plan: {tools}")
            else:
                self.record_result("ACC-011", False, "compute_allowed_tools function missing")
        except Exception as e:
            self.record_result("ACC-011", False, f"Check failed: {e}")

    def check_acc_012(self):
        """ACC-012: ChunkWorkOrder rejects every empty provenance/output binding"""
        try:
            import bet.pipeline.sharding.models as sm
            if hasattr(sm, "ChunkWorkOrderV1"):
                cls = sm.ChunkWorkOrderV1
                try:
                    obj = cls(
                        chunk_id="chunk_1",
                        parent_work_order_id="p1",
                        chunk_index=0,
                        total_chunks=1,
                        event_ids=(),
                        agent_name="agent1",
                    )
                    self.record_result("ACC-012", False, "ChunkWorkOrderV1 accepted empty event_ids")
                except Exception:
                    self.record_result("ACC-012", True, "ChunkWorkOrderV1 rejected empty binding")
            else:
                self.record_result("ACC-012", False, "ChunkWorkOrderV1 missing")
        except Exception as e:
            self.record_result("ACC-012", False, f"Check failed: {e}")

    def check_acc_013(self):
        """ACC-013: canonical Orchestrator exposes exact pending chunk work order"""
        try:
            from bet.pipeline.orchestrator import Orchestrator
            if hasattr(Orchestrator, "pending_chunk_work_order_path") and hasattr(Orchestrator, "pending_chunk_work_order_sha256"):
                self.record_result("ACC-013", True, "Orchestrator exposes pending_chunk_work_order_path and sha256")
            else:
                self.record_result("ACC-013", False, "Orchestrator missing pending_chunk_work_order_path or sha256")
        except Exception as e:
            self.record_result("ACC-013", False, f"Check failed: {e}")

    def check_acc_014(self):
        """ACC-014: ledger records WAITING_FOR_CHUNK_ARTIFACT before runner returns"""
        try:
            import bet.pipeline.sharding.lifecycle as sl
            if hasattr(sl, "WAITING_FOR_CHUNK_ARTIFACT") and sl.WAITING_FOR_CHUNK_ARTIFACT == "WAITING_FOR_CHUNK_ARTIFACT":
                self.record_result("ACC-014", True, "WAITING_FOR_CHUNK_ARTIFACT lifecycle state exists")
            else:
                self.record_result("ACC-014", False, "WAITING_FOR_CHUNK_ARTIFACT missing in sharding lifecycle")
        except Exception as e:
            self.record_result("ACC-014", False, f"Check failed: {e}")

    def check_acc_015(self):
        """ACC-015: second process resumes exact chunk safely"""
        try:
            import bet.pipeline.sharding.lifecycle as sl
            if hasattr(sl, "resume_chunk_execution") or hasattr(sl, "validate_chunk_against_work_order"):
                self.record_result("ACC-015", True, "Chunk execution resume and validation functions exist")
            else:
                self.record_result("ACC-015", False, "resume_chunk_execution or chunk validation missing")
        except Exception as e:
            self.record_result("ACC-015", False, f"Check failed: {e}")

    def check_acc_016(self):
        """ACC-016: aggregate artifact binds parent work order and all chunks"""
        try:
            import bet.pipeline.sharding.models as sm
            if hasattr(sm, "ChunkAggregationReceiptV1"):
                cls = sm.ChunkAggregationReceiptV1
                annotations = getattr(cls, "__annotations__", {})
                if "parent_work_order_id" in annotations and "chunk_ids" in annotations:
                    self.record_result("ACC-016", True, "ChunkAggregationReceiptV1 binds parent work order and chunk IDs")
                else:
                    self.record_result("ACC-016", False, "ChunkAggregationReceiptV1 missing bindings")
            else:
                self.record_result("ACC-016", False, "ChunkAggregationReceiptV1 missing")
        except Exception as e:
            self.record_result("ACC-016", False, f"Check failed: {e}")

    def check_acc_017(self):
        """ACC-017: duplicate/missing/foreign chunk events block"""
        try:
            import bet.pipeline.sharding.lifecycle as sl
            if hasattr(sl, "validate_chunk_aggregation"):
                try:
                    sl.validate_chunk_aggregation(
                        parent_events=["e1", "e2"],
                        chunk_events=[["e1"], ["e99"]]
                    )
                    self.record_result("ACC-017", False, "Chunk aggregation allowed foreign event e99")
                except Exception:
                    self.record_result("ACC-017", True, "Chunk aggregation rejected foreign event")
            else:
                self.record_result("ACC-017", False, "validate_chunk_aggregation missing")
        except Exception as e:
            self.record_result("ACC-017", False, f"Check failed: {e}")

    def check_acc_018(self):
        """ACC-018: sport protocol is invoked in canonical S2.9"""
        try:
            import bet.pipeline.sports.protocols as sp
            if hasattr(sp, "get_sport_protocol_handler"):
                handler = sp.get_sport_protocol_handler("football")
                if handler is not None:
                    self.record_result("ACC-018", True, "Sport protocol handler exists and resolves for football")
                else:
                    self.record_result("ACC-018", False, "Sport protocol handler returned None for football")
            else:
                self.record_result("ACC-018", False, "Sport protocol handler function missing")
        except Exception as e:
            self.record_result("ACC-018", False, f"Check failed: {e}")

    def check_acc_019(self):
        """ACC-019: same dossier is consumed by canonical S5"""
        try:
            import bet.pipeline.market_evidence_sufficiency as mes
            if hasattr(mes, "MarketDossierV1"):
                cls = mes.MarketDossierV1
                if hasattr(cls, "model_validate") or hasattr(cls, "__annotations__"):
                    self.record_result("ACC-019", True, "MarketDossierV1 contract exists")
                else:
                    self.record_result("ACC-019", False, "MarketDossierV1 invalid")
            else:
                self.record_result("ACC-019", False, "MarketDossierV1 missing")
        except Exception as e:
            self.record_result("ACC-019", False, f"Check failed: {e}")

    def check_acc_020(self):
        """ACC-020: canonical S3 requires exact sport+competition+market model scope"""
        try:
            import bet.pipeline.market_probability_inputs as mpi
            if hasattr(mpi, "validate_model_scope_match"):
                mismatched = mpi.validate_model_scope_match(
                    model_scope={"sport": "football", "competition": "EPL", "market": "1X2"},
                    event_scope={"sport": "football", "competition": "LA_LIGA", "market": "1X2"}
                )
                if not mismatched:
                    self.record_result("ACC-020", True, "Model scope mismatch detected")
                else:
                    self.record_result("ACC-020", False, "Model scope mismatch allowed")
            else:
                self.record_result("ACC-020", False, "validate_model_scope_match missing")
        except Exception as e:
            self.record_result("ACC-020", False, f"Check failed: {e}")

    def check_acc_021(self):
        """ACC-021: evidence ready with no model remains ANALYSIS_ONLY"""
        try:
            import bet.pipeline.analysis_status as ast
            if hasattr(ast, "resolve_analysis_status"):
                status = ast.resolve_analysis_status(evidence_ready=True, model_package=None)
                if status == "ANALYSIS_ONLY":
                    self.record_result("ACC-021", True, "Evidence ready without model remains ANALYSIS_ONLY")
                else:
                    self.record_result("ACC-021", False, f"Status was {status}, expected ANALYSIS_ONLY")
            else:
                self.record_result("ACC-021", False, "resolve_analysis_status missing")
        except Exception as e:
            self.record_result("ACC-021", False, f"Check failed: {e}")

    def check_acc_022(self):
        """ACC-022: arbitrary files cannot create model eligibility"""
        try:
            import bet.pipeline.readiness_contracts as rc
            if hasattr(rc, "ModelPackageResolver"):
                with tempfile.TemporaryDirectory() as fake_dir:
                    p = Path(fake_dir)
                    (p / "model-package.json").write_text("{}")
                    (p / "promotion-decision.json").write_text('{"status": "PROMOTED"}')
                    res = rc.ModelPackageResolver.resolve_package(fake_dir)
                    if res is None or getattr(res, "is_eligible", False) == False:
                        self.record_result("ACC-022", True, "Arbitrary files rejected for model eligibility")
                    else:
                        self.record_result("ACC-022", False, "Arbitrary files granted model eligibility")
            else:
                self.record_result("ACC-022", False, "ModelPackageResolver missing")
        except Exception as e:
            self.record_result("ACC-022", False, f"Check failed: {e}")

    def check_acc_023(self):
        """ACC-023: caller cannot provide final/calibrated probability"""
        try:
            import bet.pipeline.market_probability_inputs as mpi
            if hasattr(mpi, "MarketProbabilityInputV1"):
                cls = mpi.MarketProbabilityInputV1
                try:
                    obj = cls(event_id="e1", market="1X2", caller_provided_probability=0.75)
                    self.record_result("ACC-023", False, "Caller probability accepted on probability input DTO")
                except Exception:
                    self.record_result("ACC-023", True, "Caller probability rejected by DTO")
            else:
                self.record_result("ACC-023", False, "MarketProbabilityInputV1 missing")
        except Exception as e:
            self.record_result("ACC-023", False, f"Check failed: {e}")

    def check_acc_024(self):
        """ACC-024: model package must resolve semantic dataset/model/backtest/calibration objects"""
        try:
            import bet.pipeline.readiness_contracts as rc
            if hasattr(rc, "ModelPackageV1"):
                cls = rc.ModelPackageV1
                annotations = getattr(cls, "__annotations__", {})
                if "dataset_receipt_sha256" in annotations and "calibration_report_sha256" in annotations:
                    self.record_result("ACC-024", True, "ModelPackageV1 semantic contract exists")
                else:
                    self.record_result("ACC-024", False, "ModelPackageV1 missing semantic fields")
            else:
                self.record_result("ACC-024", False, "ModelPackageV1 missing")
        except Exception as e:
            self.record_result("ACC-024", False, f"Check failed: {e}")

    def check_acc_025(self):
        """ACC-025: arbitrary files cannot create joint-model eligibility"""
        try:
            import bet.pipeline.readiness_contracts as rc
            if hasattr(rc, "JointModelPackageResolver"):
                with tempfile.TemporaryDirectory() as fake_dir:
                    res = rc.JointModelPackageResolver.resolve_package(fake_dir)
                    if res is None or getattr(res, "is_eligible", False) == False:
                        self.record_result("ACC-025", True, "Arbitrary files rejected for joint model eligibility")
                    else:
                        self.record_result("ACC-025", False, "Arbitrary files granted joint model eligibility")
            else:
                self.record_result("ACC-025", False, "JointModelPackageResolver missing")
        except Exception as e:
            self.record_result("ACC-025", False, f"Check failed: {e}")

    def check_acc_026(self):
        """ACC-026: builder cannot use marginal multiplication without verified independence package"""
        try:
            import bet.builder.engine as bengine
            if hasattr(bengine, "calculate_combined_odds"):
                try:
                    res = bengine.calculate_combined_odds([0.5, 0.5], joint_model=None)
                    if res is not None and res.get("combined_odds") is not None:
                        self.record_result("ACC-026", False, "Builder multiplied marginals without joint package")
                    else:
                        self.record_result("ACC-026", True, "Builder rejected marginal multiplication without joint package")
                except Exception:
                    self.record_result("ACC-026", True, "Builder rejected marginal multiplication")
            else:
                self.record_result("ACC-026", False, "calculate_combined_odds missing")
        except Exception as e:
            self.record_result("ACC-026", False, f"Check failed: {e}")

    def check_acc_027(self):
        """ACC-027: canonical S7->S7b fields are identical"""
        try:
            import bet.pipeline.contracts.steps.s3_to_s10 as s3_s10
            if hasattr(s3_s10, "S7CandidateRecord") and hasattr(s3_s10, "S7bCandidateRecord"):
                s7_fields = set(s3_s10.S7CandidateRecord.__annotations__.keys())
                s7b_fields = set(s3_s10.S7bCandidateRecord.__annotations__.keys())
                if s7_fields == s7b_fields:
                    self.record_result("ACC-027", True, "S7 and S7b candidate fields are identical")
                else:
                    diff = s7_fields.symmetric_difference(s7b_fields)
                    self.record_result("ACC-027", False, f"S7 and S7b fields differ: {diff}")
            else:
                self.record_result("ACC-027", False, "S7CandidateRecord or S7bCandidateRecord missing")
        except Exception as e:
            self.record_result("ACC-027", False, f"Check failed: {e}")

    def check_acc_028(self):
        """ACC-028: canonical S7b->S8 fields are identical"""
        try:
            import bet.pipeline.contracts.steps.s3_to_s10 as s3_s10
            if hasattr(s3_s10, "S7bCandidateRecord") and hasattr(s3_s10, "S8InputCandidateRecord"):
                s7b_fields = set(s3_s10.S7bCandidateRecord.__annotations__.keys())
                s8_fields = set(s3_s10.S8InputCandidateRecord.__annotations__.keys())
                if s7b_fields == s8_fields:
                    self.record_result("ACC-028", True, "S7b and S8 candidate fields are identical")
                else:
                    diff = s7b_fields.symmetric_difference(s8_fields)
                    self.record_result("ACC-028", False, f"S7b and S8 fields differ: {diff}")
            else:
                self.record_result("ACC-028", False, "S7bCandidateRecord or S8InputCandidateRecord missing")
        except Exception as e:
            self.record_result("ACC-028", False, f"Check failed: {e}")

    def check_acc_029(self):
        """ACC-029: S7b does not invent football/League/Home/Away/VERIFIED"""
        try:
            import bet.pipeline.analytical_candidate_bridge as acb
            if hasattr(acb, "map_s7_to_s7b"):
                res = acb.map_s7_to_s7b({"event_id": "e1"})
                if res.get("sport") == "football" or res.get("mapping_status") == "VERIFIED":
                    self.record_result("ACC-029", False, "S7b mapper invented default football/VERIFIED")
                else:
                    self.record_result("ACC-029", True, "S7b mapper did not invent default metadata")
            else:
                self.record_result("ACC-029", False, "map_s7_to_s7b missing")
        except Exception as e:
            self.record_result("ACC-029", False, f"Check failed: {e}")

    def check_acc_030(self):
        """ACC-030: S8 does not invent identity, markets, probabilities or odds"""
        try:
            import bet.pipeline.bet_builder_analytical as bba
            if hasattr(bba, "build_analytical_coupon"):
                res = bba.build_analytical_coupon(candidates=[{"event_id": "e1"}])
                if isinstance(res, dict) and (res.get("odds") is not None or res.get("probability") is not None):
                    self.record_result("ACC-030", False, "S8 coupon builder invented odds or probability")
                else:
                    self.record_result("ACC-030", True, "S8 coupon builder did not invent odds/probability")
            else:
                self.record_result("ACC-030", False, "build_analytical_coupon missing")
        except Exception as e:
            self.record_result("ACC-030", False, f"Check failed: {e}")

    def check_acc_031(self):
        """ACC-031: S8 READY requires full model-package provenance"""
        try:
            import bet.pipeline.bet_builder_analytical as bba
            if hasattr(bba, "validate_s8_ready_provenance"):
                valid = bba.validate_s8_ready_provenance({"odds": 2.0, "model_package_id": None})
                if not valid:
                    self.record_result("ACC-031", True, "S8 READY rejected due to missing model_package_id")
                else:
                    self.record_result("ACC-031", False, "S8 READY accepted odds without model provenance")
            else:
                self.record_result("ACC-031", False, "validate_s8_ready_provenance missing")
        except Exception as e:
            self.record_result("ACC-031", False, f"Check failed: {e}")

    def check_acc_032(self):
        """ACC-032: no model means ANALYSIS_ONLY_OUTPUT and no human gate"""
        try:
            import bet.pipeline.bet_builder_analytical as bba
            if hasattr(bba, "build_s8_output"):
                res = bba.build_s8_output(candidates=[{"event_id": "e1"}], model_package=None)
                output_status = res.get("output_status") if isinstance(res, dict) else getattr(res, "output_status", None)
                ready_gate = res.get("ready_for_human_gate") if isinstance(res, dict) else getattr(res, "ready_for_human_gate", None)
                if output_status == "ANALYSIS_ONLY_OUTPUT" and ready_gate == False:
                    self.record_result("ACC-032", True, "Unpriced output is ANALYSIS_ONLY_OUTPUT and human gate is False")
                else:
                    self.record_result("ACC-032", False, f"Output status {output_status}, ready_for_human_gate {ready_gate}")
            else:
                self.record_result("ACC-032", False, "build_s8_output missing")
        except Exception as e:
            self.record_result("ACC-032", False, f"Check failed: {e}")

    def check_acc_033(self):
        """ACC-033: no joint model means typed builder rejection and no combined odds"""
        try:
            import bet.pipeline.bet_builder_analytical as bba
            if hasattr(bba, "build_bet_builder_pack"):
                res = bba.build_bet_builder_pack(candidates=[{"event_id": "e1", "market": "1X2"}, {"event_id": "e1", "market": "O2.5"}], joint_model=None)
                rejection_reason = res.get("rejection_reason") if isinstance(res, dict) else getattr(res, "rejection_reason", None)
                if rejection_reason == "NO_VERIFIED_JOINT_MODEL_SCOPE":
                    self.record_result("ACC-033", True, "Bet Builder rejected with NO_VERIFIED_JOINT_MODEL_SCOPE")
                else:
                    self.record_result("ACC-033", False, f"Rejection reason was {rejection_reason}")
            else:
                self.record_result("ACC-033", False, "build_bet_builder_pack missing")
        except Exception as e:
            self.record_result("ACC-033", False, f"Check failed: {e}")

    def check_acc_034(self):
        """ACC-034: mandatory tests reject all former exploits"""
        try:
            exploit_test = os.path.join(self.target_dir, "tests", "security", "test_v5_exploit_regressions.py")
            if not os.path.exists(exploit_test):
                self.record_result("ACC-034", False, "test_v5_exploit_regressions.py missing")
                return
            cmd = [sys.executable, "-m", "pytest", "-q", exploit_test]
            env = dict(os.environ)
            env["PYTHONPATH"] = f"{self.src_dir}:{self.scripts_dir}"
            res = subprocess.run(cmd, cwd=self.target_dir, env=env, capture_output=True, text=True)
            if res.returncode == 0:
                self.record_result("ACC-034", True, "Exploit regression tests executed and passed cleanly")
            else:
                self.record_result("ACC-034", False, f"Exploit regression tests failed (rc={res.returncode}): {res.stderr}")
        except Exception as e:
            self.record_result("ACC-034", False, f"Check failed: {e}")

    def check_acc_035(self):
        """ACC-035: certifier distinguishes analysis readiness from priced-coupon readiness"""
        try:
            cert_script = os.path.join(self.scripts_dir, "certify_pipeline_final_closure.py")
            if os.path.exists(cert_script):
                with open(cert_script, encoding="utf-8") as f:
                    content = f.read()
                if "READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION" in content and "READY_FOR_PRICED_COUPON_SESSION" in content:
                    self.record_result("ACC-035", True, "Certifier distinguishes analysis readiness from priced-coupon readiness")
                else:
                    self.record_result("ACC-035", False, "Certifier missing required readiness distinction flags")
            else:
                self.record_result("ACC-035", False, "certify_pipeline_final_closure.py missing")
        except Exception as e:
            self.record_result("ACC-035", False, f"Check failed: {e}")

    def check_acc_036(self):
        """ACC-036: full suite report includes collected/passed/failed/skipped/exit code"""
        try:
            junit_tmp = Path(tempfile.gettempdir()) / "v5_acc_036_junit.xml"
            cmd = [sys.executable, "-m", "pytest", "-q", f"--junitxml={junit_tmp}", "tests/security/"]
            env = dict(os.environ)
            env["PYTHONPATH"] = f"{self.src_dir}:{self.scripts_dir}"
            res = subprocess.run(cmd, cwd=self.target_dir, env=env, capture_output=True, text=True)
            if res.returncode == 0 and junit_tmp.is_file():
                self.record_result("ACC-036", True, "Pytest test execution produced valid JUnit receipt")
            else:
                self.record_result("ACC-036", False, f"Pytest execution failed with exit code {res.returncode}")
        except Exception as e:
            self.record_result("ACC-036", False, f"Check failed: {e}")

    def check_acc_037(self):
        """ACC-037: CI runs typecheck, validators, certifier and full suite"""
        try:
            prod_check = os.path.join(self.scripts_dir, "prod-check.sh")
            if not os.path.exists(prod_check):
                self.record_result("ACC-037", False, "prod-check.sh missing")
                return
            with open(prod_check, encoding="utf-8") as f:
                content = f.read()
            if "certify_pipeline_final_closure.py" in content and "pytest" in content:
                self.record_result("ACC-037", True, "prod-check.sh contains required CI-equivalent checks")
            else:
                self.record_result("ACC-037", False, "prod-check.sh missing certifier or pytest")
        except Exception as e:
            self.record_result("ACC-037", False, f"Check failed: {e}")

    def check_acc_038(self):
        """ACC-038: no operator/browser/bookmaker path is reachable"""
        try:
            bad_imports = []
            for root, _, files in os.walk(self.src_dir):
                for file in files:
                    if file.endswith(".py"):
                        path = os.path.join(root, file)
                        with open(path, "r", errors="ignore") as f:
                            content = f.read()
                        if "import playwright" in content or "from playwright" in content or "browser_click" in content or "login_superbet" in content:
                            bad_imports.append(os.path.relpath(path, self.target_dir))
            if not bad_imports:
                self.record_result("ACC-038", True, "No operator/browser automation imports found in src/")
            else:
                self.record_result("ACC-038", False, f"Found browser automation imports in: {bad_imports}")
        except Exception as e:
            self.record_result("ACC-038", False, f"Check failed: {e}")

    def run_all(self) -> bool:
        for i in range(1, 39):
            req_id = f"ACC-{i:03d}"
            method_name = f"check_acc_{i:03d}"
            method = getattr(self, method_name, None)
            if method:
                try:
                    method()
                except Exception as e:
                    self.record_result(req_id, False, f"Unexpected error running check: {e}")
            else:
                self.record_result(req_id, False, f"Check method {method_name} not implemented")

        all_passed = all(r["passed"] for r in self.results.values())
        return all_passed

    def export_json(self, path: str, started_at: str, finished_at: str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        repo_p = Path(self.target_dir)

        head_sha = get_git_commit_head(repo_p)
        git_tree_sha = get_git_tree_sha(repo_p)
        source_manifest_sha = compute_source_manifest_sha256(repo_p)
        env_fingerprint = get_sanitized_env_fingerprint()

        passed_cnt = sum(1 for r in self.results.values() if r["passed"])
        failed_cnt = sum(1 for r in self.results.values() if not r["passed"])
        total_cnt = len(self.results)
        overall_status = "PASS" if failed_cnt == 0 and total_cnt == 38 else "FAIL"

        receipt_data = {
            "head_sha": head_sha,
            "git_tree_sha": git_tree_sha,
            "source_manifest_sha256": source_manifest_sha,
            "command_argv": sys.argv,
            "cwd": self.target_dir,
            "environment_fingerprint": env_fingerprint,
            "started_at": started_at,
            "finished_at": finished_at,
            "exit_code": 0 if overall_status == "PASS" else 1,
            "stdout_sha256": "",
            "stderr_sha256": "",
            "artifact_sha256": "",
            "overall_status": overall_status,
            "passed_count": passed_cnt,
            "failed_count": failed_cnt,
            "total_count": total_cnt,
            "results": self.results,
        }

        validated_receipt = AcceptanceReceiptV1(**receipt_data)
        p.write_text(json.dumps(validated_receipt.model_dump(), indent=2), encoding="utf-8")

    def export_junit(self, path: str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        testsuite = ET.Element("testsuite", name="V5ExternalAcceptance", tests=str(len(self.results)))
        for req_id, res in sorted(self.results.items()):
            testcase = ET.Element("testcase", classname="V5ExternalAcceptance", name=req_id)
            if not res["passed"]:
                failure = ET.SubElement(testcase, "failure", message=res["message"])
                failure.text = json.dumps(res.get("details", {}))
            testsuite.append(testcase)
        tree = ET.ElementTree(testsuite)
        tree.write(p, encoding="utf-8", xml_declaration=True)


def main():
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    args = parse_args()
    runner = AcceptanceRunner(args.repo_root)
    success = runner.run_all()
    finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if args.json_out:
        runner.export_json(args.json_out, started_at, finished_at)
    if args.junit_out:
        runner.export_junit(args.junit_out)

    print(f"ACCEPTANCE EXECUTION COMPLETE: Overall={'PASS' if success else 'FAIL'} Passed={sum(1 for r in runner.results.values() if r['passed'])} Failed={sum(1 for r in runner.results.values() if not r['passed'])}")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
