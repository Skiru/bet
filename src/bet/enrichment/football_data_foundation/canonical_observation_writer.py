from __future__ import annotations

import datetime
import hashlib
import sqlite3
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from bet.enrichment.football_data_foundation.canonical_fixture_resolver import (
    CanonicalFixtureResolutionResult,
    table_exists,
)
from bet.enrichment.football_data_foundation.scanner_bridge import ScannerEnrichmentRunRecord


@dataclass(frozen=True)
class ObservationWriteResult:
    status: str
    fixture_id: int | None
    observation_ids: tuple[int, ...]
    projection_ids: tuple[int, ...]
    evidence_package_id: str | None
    run_id: int | None
    attempt_ids: tuple[int, ...]
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


def write_enrichment_observations(
    conn: sqlite3.Connection,
    resolution: CanonicalFixtureResolutionResult,
    bridge_result: ScannerEnrichmentRunRecord,
    analysis_cutoff_at: str,
) -> ObservationWriteResult:
    """Write enrichment facts and completeness state into existing repository observation
    and sports enrichment tables using temp SQLite connection.
    """
    if resolution.fixture_id is None:
        return ObservationWriteResult(
            status="BLOCKED_FIXTURE_NOT_RESOLVED",
            fixture_id=None,
            observation_ids=(),
            projection_ids=(),
            evidence_package_id=None,
            run_id=None,
            attempt_ids=(),
            diagnostics={"error": "Cannot write observations for unresolved fixture"},
        )

    fixture_id = resolution.fixture_id
    home_team_id = resolution.home_team_id
    away_team_id = resolution.away_team_id
    profile_id = bridge_result.profile_id
    scanner_event_id = bridge_result.scanner_event_id

    diagnostics: dict[str, Any] = {}
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        # 1. Create evidence_package_revision rows
        evidence_package_id = None
        for evidence_identity in bridge_result.evidence_identities:
            # Generate package ID
            package_id = f"pkg_{evidence_identity}"
            evidence_package_id = package_id
            
            # Find provider_id from completeness state
            provider_id = "espn-fifa-worldcup"
            for state in bridge_result.completeness_state:
                if state.evidence_identity == evidence_identity:
                    provider_id = state.provider_id
                    break
                    
            cursor = conn.execute(
                "SELECT id FROM evidence_package_revision WHERE package_id = ?",
                (package_id,),
            )
            row = cursor.fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO evidence_package_revision "
                    "(package_id, source_key, operation_name, request_identity, parser_version, dto_version, revision_hash, member_count, completeness_state, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        package_id,
                        provider_id,
                        "scanner_event_enrichment",
                        f"{profile_id}:{scanner_event_id}:{evidence_identity}",
                        "1.0.0",
                        "1",
                        evidence_identity,
                        len(bridge_result.facts),
                        "COMPLETE_FRESH",
                        now_str,
                    ),
                )

        # 2. Create sports_enrichment_run row
        run_identity = f"run_{profile_id}_{scanner_event_id}_{analysis_cutoff_at}"
        cursor = conn.execute(
            "SELECT id FROM sports_enrichment_run WHERE run_identity = ?",
            (run_identity,),
        )
        run_row = cursor.fetchone()
        if run_row:
            run_id = run_row[0]
        else:
            caps = [d.get("capability") for d in bridge_result.fetch_decisions if d.get("capability")]
            if not caps:
                caps = ["current_discovery", "detailed_metrics", "current_form"]
            requested_capabilities_str = ",".join(caps)
            cursor = conn.execute(
                "INSERT INTO sports_enrichment_run "
                "(run_identity, sport, canonical_event_id, analysis_cutoff_at, status, started_at, completed_at, policy_config_hash, requested_capabilities, completion_summary) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_identity,
                    "football",
                    fixture_id,
                    analysis_cutoff_at,
                    "COMPLETED",
                    now_str,
                    now_str,
                    "default",
                    requested_capabilities_str,
                    "Proof of concept enrichment mapping run completed successfully",
                ),
            )
            run_id = cursor.lastrowid

        # 3. Create source_operation_attempt rows
        attempt_ids: list[int] = []
        for idx, decision in enumerate(bridge_result.fetch_decisions):
            capability = decision.get("capability", "current_discovery")
            attempt_identity = f"attempt_{profile_id}_{scanner_event_id}_{capability}_{analysis_cutoff_at}"
            
            cursor = conn.execute(
                "SELECT id FROM source_operation_attempt WHERE attempt_identity = ?",
                (attempt_identity,),
            )
            att_row = cursor.fetchone()
            if att_row:
                attempt_ids.append(att_row[0])
            else:
                provider_priority = decision.get("provider_priority", ["espn-fifa-worldcup"])
                provider = provider_priority[0] if provider_priority else "espn-fifa-worldcup"
                
                cursor = conn.execute(
                    "INSERT INTO source_operation_attempt "
                    "(attempt_identity, run_id, provider, operation, request_identity, status, started_at, completed_at, http_status, retry_count, parser_version, dto_version, evidence_bundle_id, selectable, diagnostics) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        attempt_identity,
                        run_id,
                        provider,
                        capability,
                        f"req_{profile_id}_{scanner_event_id}_{capability}",
                        "COMPLETED",
                        now_str,
                        now_str,
                        200,
                        0,
                        "1.0.0",
                        "1",
                        bridge_result.evidence_identities[0] if bridge_result.evidence_identities else "",
                        1,
                        json.dumps(decision),
                    ),
                )
                attempt_ids.append(cursor.lastrowid)

        # 4. Group facts by (capability, evidence_identity) to build payloads
        # We need to construct home-team and away-team payloads for each capability
        facts_by_group: dict[tuple[str, str], list[Any]] = {}
        for fact in bridge_result.facts:
            group_key = (fact.capability, fact.evidence_identity)
            if group_key not in facts_by_group:
                facts_by_group[group_key] = []
            facts_by_group[group_key].append(fact)

        observation_ids: list[int] = []
        projection_ids: list[int] = []

        # Map group payloads to team-specific observations
        for (capability, evidence_identity), group_facts in facts_by_group.items():
            home_payload: dict[str, Any] = {}
            away_payload: dict[str, Any] = {}

            # Find provider for this group
            source_provider = "espn-fifa-worldcup"
            for state in bridge_result.completeness_state:
                if state.evidence_identity == evidence_identity:
                    source_provider = state.provider_id
                    break

            for fact in group_facts:
                fact_name = fact.fact_name
                fact_val = fact.fact_value_num if fact.fact_value_num is not None else fact.fact_value_text
                
                # Deterministic team mapping policy
                if "home_" in fact_name or fact_name.endswith("_home"):
                    home_payload[fact_name] = fact_val
                elif "away_" in fact_name or fact_name.endswith("_away"):
                    away_payload[fact_name] = fact_val
                else:
                    # Fixture-level fact: copy to both teams
                    home_payload[fact_name] = fact_val
                    away_payload[fact_name] = fact_val

            # Write observation for home team
            if home_payload and home_team_id is not None:
                home_payload_str = json.dumps(home_payload, sort_keys=True)
                home_sha = hashlib.sha256(home_payload_str.encode("utf-8")).hexdigest()
                logical_identity = f"obs_{fixture_id}_{home_team_id}_{capability}_{evidence_identity}"
                
                cursor = conn.execute(
                    "SELECT id FROM fixture_capability_observation WHERE logical_identity = ?",
                    (logical_identity,),
                )
                obs_row = cursor.fetchone()
                if obs_row:
                    home_obs_id = obs_row[0]
                    observation_ids.append(home_obs_id)
                else:
                    cursor = conn.execute(
                        "INSERT INTO fixture_capability_observation "
                        "(canonical_fixture_id, team_id, capability, source, request_identity, evidence_bundle_id, native_fixture_id, status, http_status, observed_at, valid_at, payload_sha256, payload_json, logical_identity, evidence_package_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            fixture_id,
                            home_team_id,
                            capability,
                            source_provider,
                            f"{profile_id}:{scanner_event_id}:{evidence_identity}",
                            evidence_identity,
                            resolution.provider_event_id,
                            "SUCCESS",
                            200,
                            now_str,
                            now_str,
                            home_sha,
                            home_payload_str,
                            logical_identity,
                            f"pkg_{evidence_identity}",
                        ),
                    )
                    home_obs_id = cursor.lastrowid
                    observation_ids.append(home_obs_id)

                # Write projection for home team
                proj_cursor = conn.execute(
                    "SELECT id FROM fixture_capability_projection "
                    "WHERE canonical_fixture_id = ? AND team_id = ? AND capability = ? AND analysis_cutoff_at = ?",
                    (fixture_id, home_team_id, capability, analysis_cutoff_at),
                )
                proj_row = proj_cursor.fetchone()
                if proj_row:
                    projection_ids.append(proj_row[0])
                else:
                    cursor = conn.execute(
                        "INSERT INTO fixture_capability_projection "
                        "(canonical_fixture_id, team_id, capability, analysis_cutoff_at, selected_source, selected_status, selected_observation_id, primary_source, primary_status, created_at, updated_at, snapshot_run_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            fixture_id,
                            home_team_id,
                            capability,
                            analysis_cutoff_at,
                            source_provider,
                            "SUCCESS",
                            home_obs_id,
                            source_provider,
                            "SUCCESS",
                            now_str,
                            now_str,
                            run_id,
                        ),
                    )
                    projection_ids.append(cursor.lastrowid)

            # Write observation for away team
            if away_payload and away_team_id is not None:
                away_payload_str = json.dumps(away_payload, sort_keys=True)
                away_sha = hashlib.sha256(away_payload_str.encode("utf-8")).hexdigest()
                logical_identity = f"obs_{fixture_id}_{away_team_id}_{capability}_{evidence_identity}"
                
                cursor = conn.execute(
                    "SELECT id FROM fixture_capability_observation WHERE logical_identity = ?",
                    (logical_identity,),
                )
                obs_row = cursor.fetchone()
                if obs_row:
                    away_obs_id = obs_row[0]
                    observation_ids.append(away_obs_id)
                else:
                    cursor = conn.execute(
                        "INSERT INTO fixture_capability_observation "
                        "(canonical_fixture_id, team_id, capability, source, request_identity, evidence_bundle_id, native_fixture_id, status, http_status, observed_at, valid_at, payload_sha256, payload_json, logical_identity, evidence_package_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            fixture_id,
                            away_team_id,
                            capability,
                            source_provider,
                            f"{profile_id}:{scanner_event_id}:{evidence_identity}",
                            evidence_identity,
                            resolution.provider_event_id,
                            "SUCCESS",
                            200,
                            now_str,
                            now_str,
                            away_sha,
                            away_payload_str,
                            logical_identity,
                            f"pkg_{evidence_identity}",
                        ),
                    )
                    away_obs_id = cursor.lastrowid
                    observation_ids.append(away_obs_id)

                # Write projection for away team
                proj_cursor = conn.execute(
                    "SELECT id FROM fixture_capability_projection "
                    "WHERE canonical_fixture_id = ? AND team_id = ? AND capability = ? AND analysis_cutoff_at = ?",
                    (fixture_id, away_team_id, capability, analysis_cutoff_at),
                )
                proj_row = proj_cursor.fetchone()
                if proj_row:
                    projection_ids.append(proj_row[0])
                else:
                    cursor = conn.execute(
                        "INSERT INTO fixture_capability_projection "
                        "(canonical_fixture_id, team_id, capability, analysis_cutoff_at, selected_source, selected_status, selected_observation_id, primary_source, primary_status, created_at, updated_at, snapshot_run_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            fixture_id,
                            away_team_id,
                            capability,
                            analysis_cutoff_at,
                            source_provider,
                            "SUCCESS",
                            away_obs_id,
                            source_provider,
                            "SUCCESS",
                            now_str,
                            now_str,
                            run_id,
                        ),
                    )
                    projection_ids.append(cursor.lastrowid)

        return ObservationWriteResult(
            status="SUCCESS",
            fixture_id=fixture_id,
            observation_ids=tuple(observation_ids),
            projection_ids=tuple(projection_ids),
            evidence_package_id=evidence_package_id,
            run_id=run_id,
            attempt_ids=tuple(attempt_ids),
            diagnostics=diagnostics,
        )

    except Exception as e:
        return ObservationWriteResult(
            status="BLOCKED_OBSERVATION_WRITE_FAILED",
            fixture_id=fixture_id,
            observation_ids=(),
            projection_ids=(),
            evidence_package_id=None,
            run_id=None,
            attempt_ids=(),
            diagnostics={"error": str(e)},
        )
