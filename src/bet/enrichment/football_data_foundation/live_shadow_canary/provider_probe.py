import os
from typing import Any
from typing import List
from typing import Optional

from bet.enrichment.football_data_foundation.live_shadow_canary.contracts import ProviderProbeResult
from bet.enrichment.football_data_foundation.live_shadow_canary.contracts import OfficialFixtureContext
from bet.enrichment.football_data_foundation.kernel.contracts import EvidenceClaimBatch
from bet.enrichment.football_data_foundation.provider_clients.current_live import SportDBLiveClient
from bet.enrichment.football_data_foundation.provider_clients.current_live import FootballDataOrgLiveClient
from bet.enrichment.football_data_foundation.provider_clients.current_live import HighlightlyLiveClient


def run_provider_shadow_probes(
    context: OfficialFixtureContext,
    transport: Any = None,
    out_batches: Optional[List[EvidenceClaimBatch]] = None
) -> List[ProviderProbeResult]:
    results = []

    # 1. SportDB Probe
    sportdb_key = os.getenv("SPORTDB_API_KEY")
    if not sportdb_key:
        results.append(
            ProviderProbeResult(
                provider="sportdb",
                credential_env="SPORTDB_API_KEY",
                credential_present=False,
                status="SKIPPED_CREDENTIALS_MISSING",
                request_attempted=False,
                evidence_claim_count=0,
                error=None,
                selectable_for_production=False,
            )
        )
    elif not context.match_id:
        results.append(
            ProviderProbeResult(
                provider="sportdb",
                credential_env="SPORTDB_API_KEY",
                credential_present=True,
                status="BLOCKED_MISSING_PROVIDER_MATCH_ID",
                request_attempted=False,
                evidence_claim_count=0,
                error="SportDB probe blocked: match_id is missing from official context.",
                selectable_for_production=False,
            )
        )
    else:
        try:
            client = SportDBLiveClient(transport=transport)
            batch = client.fetch_match_stats(context.match_id)
            if out_batches is not None:
                out_batches.append(batch)
            results.append(
                ProviderProbeResult(
                    provider="sportdb",
                    credential_env="SPORTDB_API_KEY",
                    credential_present=True,
                    status="SUCCESS",
                    request_attempted=True,
                    evidence_claim_count=len(batch.claims),
                    error=None,
                    selectable_for_production=False,
                )
            )
        except Exception as e:
            results.append(
                ProviderProbeResult(
                    provider="sportdb",
                    credential_env="SPORTDB_API_KEY",
                    credential_present=True,
                    status="FAILED_PROVIDER_ERROR",
                    request_attempted=True,
                    evidence_claim_count=0,
                    error=str(e),
                    selectable_for_production=False,
                )
            )

    # 2. FootballDataOrg Probe
    fdorg_key = os.getenv("FOOTBALL_DATA_API_KEY")
    if not fdorg_key:
        results.append(
            ProviderProbeResult(
                provider="football-data-org",
                credential_env="FOOTBALL_DATA_API_KEY",
                credential_present=False,
                status="SKIPPED_CREDENTIALS_MISSING",
                request_attempted=False,
                evidence_claim_count=0,
                error=None,
                selectable_for_production=False,
            )
        )
    else:
        try:
            client = FootballDataOrgLiveClient(transport=transport)
            comp_code = "WC"
            batch = client.fetch_competition_standings(comp_code)
            if out_batches is not None:
                out_batches.append(batch)
            results.append(
                ProviderProbeResult(
                    provider="football-data-org",
                    credential_env="FOOTBALL_DATA_API_KEY",
                    credential_present=True,
                    status="SUCCESS",
                    request_attempted=True,
                    evidence_claim_count=len(batch.claims),
                    error=None,
                    selectable_for_production=False,
                )
            )
        except Exception as e:
            results.append(
                ProviderProbeResult(
                    provider="football-data-org",
                    credential_env="FOOTBALL_DATA_API_KEY",
                    credential_present=True,
                    status="FAILED_PROVIDER_ERROR",
                    request_attempted=True,
                    evidence_claim_count=0,
                    error=str(e),
                    selectable_for_production=False,
                )
            )

    # 3. Highlightly Probe
    highlightly_key = os.getenv("HIGHLIGHTLY_API_KEY")
    if not highlightly_key:
        results.append(
            ProviderProbeResult(
                provider="highlightly",
                credential_env="HIGHLIGHTLY_API_KEY",
                credential_present=False,
                status="SKIPPED_CREDENTIALS_MISSING",
                request_attempted=False,
                evidence_claim_count=0,
                error=None,
                selectable_for_production=False,
            )
        )
    elif not context.match_id:
        results.append(
            ProviderProbeResult(
                provider="highlightly",
                credential_env="HIGHLIGHTLY_API_KEY",
                credential_present=True,
                status="BLOCKED_MISSING_PROVIDER_MATCH_ID",
                request_attempted=False,
                evidence_claim_count=0,
                error="Highlightly probe blocked: match_id is missing from official context.",
                selectable_for_production=False,
            )
        )
    else:
        try:
            client = HighlightlyLiveClient(transport=transport)
            batch = client.fetch_match_statistics(context.match_id)
            if out_batches is not None:
                out_batches.append(batch)
            results.append(
                ProviderProbeResult(
                    provider="highlightly",
                    credential_env="HIGHLIGHTLY_API_KEY",
                    credential_present=True,
                    status="SUCCESS",
                    request_attempted=True,
                    evidence_claim_count=len(batch.claims),
                    error=None,
                    selectable_for_production=False,
                )
            )
        except Exception as e:
            results.append(
                ProviderProbeResult(
                    provider="highlightly",
                    credential_env="HIGHLIGHTLY_API_KEY",
                    credential_present=True,
                    status="FAILED_PROVIDER_ERROR",
                    request_attempted=True,
                    evidence_claim_count=0,
                    error=str(e),
                    selectable_for_production=False,
                )
            )

    return results
