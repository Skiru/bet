import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bet.db.schema import init_db
from bet.pipeline.event_runtime_contract import (
    CanonicalEventStatus,
    ProviderRequestStatus,
    build_participant_identity,
)
from bet.pipeline.launch_bridge import create_runtime_analysis_shadow_db
from bet.pipeline.provider_observation_evidence import (
    persist_provider_observation_with_evidence,
)
from bet.pipeline.runtime_event_classification import (
    RuntimeEventClassifier,
    RuntimeEventInput,
    persist_runtime_event_decisions,
)
from bet.pipeline.runtime_plan import RuntimePlanService
from bet.providers.revalidation import ProviderRevalidationResult

PLAN_NOW = datetime(2027, 7, 30, 10, 0, tzinfo=UTC)
KICKOFF = "2027-07-30T14:00:00Z"


@dataclass
class FakeExactAdapter:
    result: ProviderRevalidationResult
    calls: int = 0
    received_ids: list[str] | None = None

    def fetch_exact_event(self, *, provider_event_id, observed_at_utc):
        self.calls += 1
        if self.received_ids is None:
            self.received_ids = []
        self.received_ids.append(provider_event_id)
        if self.result.request_status is not ProviderRequestStatus.SUCCESS:
            return self.result
        return {
            "provider": self.result.provider,
            "provider_event_id": self.result.provider_event_id,
            "status": self.result.raw_provider_status,
            "kickoff": self.result.raw_observed_kickoff,
            "home": self.result.observed_home_name,
            "away": self.result.observed_away_name,
            "competition_identity_sha256": (self.result.competition_identity_sha256),
        }


def provider_result(
    *,
    request_status=ProviderRequestStatus.SUCCESS,
    canonical_status=CanonicalEventStatus.SCHEDULED,
    kickoff=KICKOFF,
    home="Team A",
    away="Team B",
    provider_event_id="provider-1",
):
    participant_sha = build_participant_identity(home, away).identity_sha256
    return ProviderRevalidationResult(
        provider="api_football",
        provider_event_id=provider_event_id,
        request_status=request_status,
        raw_provider_status=canonical_status.value,
        canonical_event_status=canonical_status,
        raw_observed_kickoff=kickoff,
        observed_kickoff_utc=kickoff,
        observed_home_name=home,
        observed_away_name=away,
        participant_identity_sha256=participant_sha,
        competition_identity_sha256="competition-1",
    )


def build_plan(tmp_path: Path, *, maximum_age=timedelta(minutes=5)):
    tmp_path.mkdir(parents=True, exist_ok=True)
    canonical = tmp_path / "canonical.db"
    conn = sqlite3.connect(canonical)
    init_db(conn)
    conn.execute("INSERT INTO sports (id, name) VALUES (1, 'football')")
    conn.execute(
        "INSERT INTO teams (id, sport_id, name) "
        "VALUES (1, 1, 'Team A'), (2, 1, 'Team B')"
    )
    conn.execute(
        """INSERT INTO fixtures (
           id, external_id, sport_id, home_team_id, away_team_id,
           kickoff, status, source, fetched_at)
           VALUES (1, 'provider-1', 1, 1, 2, ?, 'SCHEDULED',
                   'api_football', '2027-07-30T09:00:00Z')""",
        (KICKOFF,),
    )
    conn.commit()
    conn.close()

    run_root = tmp_path / "runs" / "run-1"
    shadow_result = create_runtime_analysis_shadow_db(
        canonical, run_root, "run-1", allow_overwrite=False
    )
    shadow = Path(shadow_result["shadow_db_path"])
    conn = sqlite3.connect(shadow)
    participant_sha = build_participant_identity("Team A", "Team B").identity_sha256
    attempt_id = persist_provider_observation_with_evidence(
        conn,
        {
            "run_id": "run-1",
            "phase": "PLAN",
            "attempt_number": 1,
            "canonical_event_id": "1",
            "fixture_id": 1,
            "provider": "api_football",
            "provider_event_id": "provider-1",
            "attempted_at_utc": PLAN_NOW.isoformat(),
            "request_status": "SUCCESS",
            "raw_provider_status": "NS",
            "canonical_event_status": "SCHEDULED",
            "raw_observed_kickoff": KICKOFF,
            "observed_kickoff_utc": KICKOFF,
            "observed_home_name": "Team A",
            "observed_away_name": "Team B",
            "participant_identity_sha256": participant_sha,
            "competition_identity_sha256": "competition-1",
        },
        run_root / "evidence" / "plan",
    )
    conn.row_factory = sqlite3.Row
    attempt = dict(
        conn.execute(
            "SELECT * FROM pipeline_provider_observation_attempts WHERE id = ?",
            (attempt_id,),
        ).fetchone()
    )
    attempt["evidence_valid"] = True
    event = RuntimeEventInput(
        canonical_event_id="1",
        fixture_id=1,
        betting_date=PLAN_NOW.date(),
        canonical_kickoff_utc=datetime.fromisoformat(KICKOFF.replace("Z", "+00:00")),
        participant_identity_sha256=participant_sha,
        provider_event_ids={"api_football": "provider-1"},
        current_plan_attempts=[attempt],
        reusable_complete=False,
    )
    classification = RuntimeEventClassifier().classify(
        event, PLAN_NOW, timedelta(minutes=15)
    )
    persist_runtime_event_decisions(
        conn,
        "run-1",
        "2027-07-30",
        [
            {
                "canonical_event_id": "1",
                "fixture_id": 1,
                "decision": classification.decision,
                "input_fingerprint": classification.input_fingerprint,
                "reason": classification.reason,
                "observed_status": "SCHEDULED",
                "observed_kickoff": KICKOFF,
                "provider": "api_football",
                "provider_event_id": "provider-1",
                "source_evidence_sha256": attempt["observation_envelope_sha256"],
                "previous_analysis_sha256": "chain-1",
            }
        ],
    )
    artifacts = run_root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    selection = artifacts / "selection_ledger.json"
    runtime_s1e = artifacts / "runtime_s1e.json"
    checkpoint = artifacts / "plan_checkpoint.json"
    selection.write_text(
        json.dumps({"run_id": "run-1", "events": ["1"]}, sort_keys=True),
        encoding="utf-8",
    )
    runtime_s1e.write_text(
        json.dumps({"run_id": "run-1", "events": ["1"]}, sort_keys=True),
        encoding="utf-8",
    )
    checkpoint.write_text(
        json.dumps({"run_id": "run-1", "status": "PLANNED"}, sort_keys=True),
        encoding="utf-8",
    )
    snapshot = RuntimePlanService().freeze_existing_plan(
        conn=conn,
        plan_id="plan-1",
        run_id="run-1",
        betting_date="2027-07-30",
        canonical_db_path=canonical,
        canonical_db_sha256=shadow_result["canonical_db_sha256_before"],
        shadow_db_path=shadow,
        shadow_db_initial_sha256=shadow_result["shadow_db_sha256_initial"],
        selection_ledger_path=selection,
        runtime_s1e_path=runtime_s1e,
        plan_checkpoint_path=checkpoint,
        created_at_utc=PLAN_NOW,
        maximum_age=maximum_age,
        classification_policy_sha256="policy-1",
    )
    return {
        "canonical": canonical,
        "run_root": run_root,
        "shadow": shadow,
        "shadow_result": shadow_result,
        "conn": conn,
        "snapshot": snapshot,
        "selection": selection,
        "runtime_s1e": runtime_s1e,
        "checkpoint": checkpoint,
    }
