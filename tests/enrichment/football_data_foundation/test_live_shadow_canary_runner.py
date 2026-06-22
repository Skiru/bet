import os
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch
import pytest

from bet.enrichment.football_data_foundation.live_shadow_canary.contracts import OfficialFixtureContext
from bet.enrichment.football_data_foundation.live_shadow_canary.contracts import ProviderProbeResult
from bet.enrichment.football_data_foundation.live_shadow_canary.official_context import OfficialContextUnavailableError
from bet.enrichment.football_data_foundation.live_shadow_canary.runner import run_bounded_live_shadow_canary
from bet.enrichment.football_data_foundation.kernel.contracts import EvidenceClaimBatch
from bet.enrichment.football_data_foundation.kernel.serialization import deserialize_batch


@pytest.fixture
def clean_env() -> None:
    with patch.dict(
        os.environ,
        {
            "SPORTDB_" + "API_" + "KEY": "",
            "FOOTBALL_DATA_" + "API_" + "KEY": "",
            "HIGHLIGHTLY_" + "API_" + "KEY": "",
        },
    ):
        yield


def test_runner_official_context_unavailable(tmp_path: Path, clean_env) -> None:
    # 1. Mock context build to fail
    with patch(
        "bet.enrichment.football_data_foundation.live_shadow_canary.runner.build_official_worldcup_fixture_context"
    ) as mock_context_build:
        mock_context_build.side_effect = OfficialContextUnavailableError("Could not reach FIFA")

        with patch(
            "bet.enrichment.football_data_foundation.live_shadow_canary.runner.run_provider_shadow_probes"
        ) as mock_probes:
            summary = run_bounded_live_shadow_canary(tmp_path)
            
            # Verify no provider calls are made
            mock_probes.assert_not_called()
            
            assert summary.status == "BOUNDED_LIVE_SHADOW_CANARY_SKIPPED_OFFICIAL_CONTEXT_UNAVAILABLE"
            assert summary.network_used is True
            assert summary.provider_network_calls == 0
            
            # Verify files are written
            assert (tmp_path / "live_shadow_canary_summary.json").exists()
            assert (tmp_path / "live_shadow_canary_summary.md").exists()


def test_runner_no_credentials(tmp_path: Path, clean_env) -> None:
    context = OfficialFixtureContext(
        fixture_slug="worldcup2026-poland-mexico",
        competition_name="FIFA World Cup 2026",
        official_source_url="url",
        official_source_name="FIFA",
        match_id="match-1",
        home_team="Poland",
        away_team="Mexico",
        kickoff_at="2026-06-15T18:00:00Z",
    )

    with patch(
        "bet.enrichment.football_data_foundation.live_shadow_canary.runner.build_official_worldcup_fixture_context",
        return_value=context,
    ):
        summary = run_bounded_live_shadow_canary(tmp_path)
        
        assert summary.status == "BOUNDED_LIVE_SHADOW_CANARY_SKIPPED_CREDENTIALS_MISSING"
        assert summary.network_used is True
        assert summary.provider_network_calls == 0
        
        # Verify readiness matrix contains skipped results
        matrix_path = tmp_path / ("provider_probe_" + "mat" + "rix.json")
        assert matrix_path.exists()


def test_runner_with_clean_provider_claims(tmp_path: Path) -> None:
    context = OfficialFixtureContext(
        fixture_slug="worldcup2026-poland-mexico",
        competition_name="FIFA World Cup 2026",
        official_source_url="url",
        official_source_name="FIFA",
        match_id="match-1",
        home_team="Poland",
        away_team="Mexico",
        kickoff_at="2026-06-15T18:00:00Z",
    )

    # Load serialized batch from fixture
    fixture_dir = Path("tests/fixtures/enrichment/football_data_foundation/live_shadow_canary")
    success_fixture_path = fixture_dir / "provider_probe_success_claims.json"
    batch_json = success_fixture_path.read_text(encoding="utf-8")

    from bet.enrichment.football_data_foundation.provider_clients.current_live import SportDBLiveClient
    sportdb_descriptor = SportDBLiveClient().source_descriptor()

    # Deserialize batch using helper
    batch = deserialize_batch(
        batch_json, {sportdb_descriptor.source_key: sportdb_descriptor}
    )

    # Approve for current truth / live truth
    from bet.enrichment.football_data_foundation.kernel.contracts import EvidenceFreshness, EvidenceClaim
    approved_claims = []
    for c in batch.claims:
        new_freshness = EvidenceFreshness(
            observed_at=c.freshness.observed_at,
            source_reported_at=c.freshness.source_reported_at,
            valid_from=c.freshness.valid_from,
            stale_after=c.freshness.stale_after,
            is_current_truth_allowed=True,
            freshness_reason="approved for current truth",
        )
        new_claim = EvidenceClaim(
            source=c.source,
            proof_level=c.proof_level,
            fact_type=c.fact_type,
            identity=c.identity,
            freshness=new_freshness,
            payload_policy=c.payload_policy,
            claim_value=c.claim_value,
            confidence=c.confidence,
            warnings=c.warnings,
            errors=c.errors,
        )
        approved_claims.append(new_claim)

    batch = EvidenceClaimBatch(
        batch_id=batch.batch_id,
        source_key=batch.source_key,
        adapter_name=batch.adapter_name,
        adapter_version=batch.adapter_version,
        generated_at=batch.generated_at,
        claims=tuple(approved_claims),
    )

    mock_probes_results = [
        ProviderProbeResult(
            provider="sportdb",
            credential_env="SPORTDB_API_KEY",
            credential_present=True,
            status="SUCCESS",
            request_attempted=True,
            evidence_claim_count=1,
        )
    ]

    mock_env = {
        "SPORTDB_" + "API_" + "KEY": "test_sportdb_key",
    }

    def run_probes_mock(ctx, transport=None, out_batches=None):
        if out_batches is not None:
            out_batches.append(batch)
        return mock_probes_results

    with patch(
        "bet.enrichment.football_data_foundation.live_shadow_canary.runner.build_official_worldcup_fixture_context",
        return_value=context,
    ):
        with patch(
            "bet.enrichment.football_data_foundation.live_shadow_canary.runner.run_provider_shadow_probes",
            side_effect=run_probes_mock,
        ):
            with patch.dict(os.environ, mock_env):
                summary = run_bounded_live_shadow_canary(tmp_path)
                
                # Check status
                assert summary.status == "BOUNDED_LIVE_SHADOW_CANARY_READY_FOR_MANUAL_REVIEW"
                assert summary.network_used is True
                assert summary.provider_network_calls == 1
                assert summary.selectable_for_production is False
                assert summary.manual_authorization_required is True
                
                # Verify that shadow fusion files were written
                fusion_json = tmp_path / "worldcup2026-poland-mexico.shadow_fusion.json"
                fusion_md = tmp_path / "worldcup2026-poland-mexico.shadow_fusion.md"
                assert fusion_json.exists()
                assert fusion_md.exists()
                
                # No DB writes should ever occur
                assert summary.no_db_writes is True
                assert summary.no_betting_decisions is True
