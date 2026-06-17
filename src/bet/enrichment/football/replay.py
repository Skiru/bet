# ruff: noqa: E501
import json
import logging

from bet.enrichment.football.contracts import (
    AcquiredFixture,
    AcquisitionMode,
    AcquisitionResult,
    BatchIdsCapability,
)
from bet.enrichment.football.parser import (
    parse_api_football_fixture_envelope,
    parse_api_football_statistics_envelope,
)
from bet.enrichment.football.time import parse_canonical_or_offset_datetime
from bet.integration.evidence import (
    load_bundle_manifest,
    load_evidence_object_bytes,
)

logger = logging.getLogger(__name__)

class EvidenceReplayAcquirer:
    def __init__(self, bundle_ids: tuple[str, ...] = ()):
        self.bundle_ids = tuple(bundle_ids)

    def acquire(
        self,
        *,
        competition_provider_id: str,
        season: int,
        from_date,
        to_date,
        max_fixtures: int,
        max_fallback_stats_calls: int,
        attempt_budget,
        ids_capability: BatchIdsCapability,
    ) -> AcquisitionResult:
        acquired_list = []
        for b_id in self.bundle_ids:
            # 1. Load bundle manifest
            manifest = load_bundle_manifest(b_id)
            identity = manifest.get("identity", {})

            # Find provider fixture ID from source_event_refs
            # e.g., ["api-football:123"] -> provider_fixture_id is "123"
            prov_fix_id = None
            for ref in identity.get("source_event_refs", []):
                if ":" in ref:
                    prov_fix_id = ref.split(":", 1)[1]
                    break

            if not prov_fix_id:
                raise ValueError(f"Could not extract provider fixture ID from bundle {b_id}")

            # Load evidence entries
            entries = manifest.get("entries", [])
            fixture_envelope = None
            stats_envelope = None

            fixture_refs = []
            stats_refs = []

            for ref in entries:
                body = load_evidence_object_bytes(ref.object_sha256)
                payload = json.loads(body.decode("utf-8"))

                if ref.operation in ("history_discovery", "history_details", "get_fixtures", "get_event_fixture"):
                    fixture_envelope = payload
                    fixture_refs.append(ref)
                elif ref.operation in ("history_statistics", "get_fixture_stats"):
                    stats_envelope = payload
                    stats_refs.append(ref)

            if not fixture_envelope:
                raise ValueError(f"No fixture details envelope found in bundle {b_id}")

            # Find the exact fixture matching prov_fix_id in raw response
            matched_item = None
            for item in fixture_envelope.get("response", []):
                if str(item.get("fixture", {}).get("id", "")) == prov_fix_id:
                    matched_item = item
                    break
            if not matched_item:
                if isinstance(fixture_envelope.get("response"), dict) and str(fixture_envelope["response"].get("fixture", {}).get("id", "")) == prov_fix_id:
                    matched_item = fixture_envelope["response"]

            if not matched_item:
                raise ValueError(f"Fixture {prov_fix_id} not found in replayed response for bundle {b_id}")

            # Parse pure fixture identity
            fixture_id_obj = parse_api_football_fixture_envelope(matched_item, prov_fix_id)

            # Parse stats if present
            stats_by_team = {}
            if stats_envelope:
                stats_response = stats_envelope.get("response", [])
                stats_by_team = parse_api_football_statistics_envelope(
                    stats_response,
                    fixture_id_obj.home_provider_team_id,
                    fixture_id_obj.away_provider_team_id,
                )
            else:
                # Check for embedded statistics in matched_item of fixture_envelope
                stats_list = matched_item.get("statistics", [])
                if isinstance(stats_list, list) and stats_list:
                    stats_by_team = parse_api_football_statistics_envelope(
                        stats_list,
                        fixture_id_obj.home_provider_team_id,
                        fixture_id_obj.away_provider_team_id,
                    )

            # Set observed_at to max original EvidenceRef.captured_at
            max_captured = None
            for ref in entries:
                if ref.captured_at:
                    if max_captured is None or ref.captured_at > max_captured:
                        max_captured = ref.captured_at

            if not max_captured:
                raise ValueError("MISSING_EVIDENCE_TIMESTAMP")

            observed_at_dt = parse_canonical_or_offset_datetime(max_captured)

            acquired = AcquiredFixture(
                fixture=fixture_id_obj,
                statistics_by_provider_team_id=stats_by_team,
                fixture_evidence_refs=tuple(fixture_refs),
                statistics_evidence_refs=tuple(stats_refs),
                observed_at=observed_at_dt,
                acquisition_mode=AcquisitionMode.REPLAY,
                warnings=(),
                originating_bundle_id=b_id,
            )
            acquired_list.append(acquired)

        # Reject a ReplayCommand containing mixed scope identities
        scopes = set()
        for acq in acquired_list:
            scopes.add((acq.fixture.provider_competition_id, acq.fixture.season))
        if len(scopes) > 1:
            raise ValueError("ReplayCommand contains mixed scope identities")

        return AcquisitionResult(
            fixtures=tuple(acquired_list),
            physical_attempts=0,
            retry_attempts=0,
            discovery_calls=0,
            ids_calls=0,
            statistics_calls=0,
            quota_metadata={},
            ids_capability=ids_capability,
            terminal_status="COMPLETE",
        )
