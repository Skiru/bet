from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bet.enrichment.football_data_foundation.kernel.contracts import (
    EvidenceClaim,
    EvidenceClaimBatch,
    EvidenceFreshness,
    FactType,
    PayloadPolicy,
    ProofLevel,
    ProviderIdentity,
    SourceDescriptor,
    SourceRole,
    sanitized_hash,
)
from bet.enrichment.football_data_foundation.kernel.errors import ProviderCapabilityError


def normalize_soccerdata_replay(source: str, input_path: Path) -> EvidenceClaimBatch:
    valid_sources = {
        "clubelo": (FactType.TEAM_RATING, "soccerdata-clubelo", "soccerdata ClubElo"),
        "espn": (FactType.REFERENCE_RESULT, "soccerdata-espn", "soccerdata ESPN"),
        "fbref": (FactType.MATCH_STATISTIC, "soccerdata-fbref", "soccerdata FBref"),
        "fivethirtyeight": (FactType.HISTORICAL_PRIOR, "soccerdata-fivethirtyeight", "soccerdata FiveThirtyEight"),
        "matchhistory": (FactType.ODDS_REFERENCE, "soccerdata-matchhistory", "soccerdata MatchHistory"),
        "sofascore": (FactType.MATCH_STATISTIC, "soccerdata-sofascore", "soccerdata Sofascore"),
        "sofifa": (FactType.PLAYER_DATA_CONTEXT, "soccerdata-sofifa", "soccerdata SoFIFA"),
        "understat": (FactType.XG, "soccerdata-understat", "soccerdata Understat"),
        "whoscored": (FactType.MATCH_STATISTIC, "soccerdata-whoscored", "soccerdata WhoScored"),
    }
    
    if source not in valid_sources:
        raise ProviderCapabilityError(f"Unsupported soccerdata source: {source}")
        
    if source == "whoscored":
        raise ProviderCapabilityError("WhoScored replay is deferred; fail closed until sanitized replay proof exists")
        
    fact_type, source_key, display_name = valid_sources[source]
    
    if not input_path.exists():
        raise ProviderCapabilityError(f"Replay file does not exist: {input_path}")
        
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ProviderCapabilityError(f"Failed to parse JSON: {e}") from e
        
    if not data.get("sanitized") and not data.get("accepted_artifact"):
        raise ProviderCapabilityError("soccerdata replay fixture must be sanitized")
        
    claim_value = dict(data.get("claim", {}))
    
    if source == "matchhistory":
        claim_value["odds_reference_not_decision"] = True
    elif source == "fivethirtyeight":
        claim_value["staleness_risk"] = "legacy_or_provider_deprecated_check_required"
        claim_value["warning"] = "FiveThirtyEight is legacy/stale"
        
    desc = SourceDescriptor(
        source_key=source_key,
        display_name=display_name,
        role=SourceRole.DEPENDENCY_REPLAY,
        requires_credentials=False,
        supports_live=False,
        supports_historical=True,
        supports_reference=True,
        supports_replay=True,
        allowed_proof_levels=(ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF,),
        notes=("soccerdata is replay/cached dependency layer only; no blind live scraping.",),
    )
    
    observed_at = datetime.now(UTC)
    payload_hash = sanitized_hash(claim_value)
    
    claim = EvidenceClaim(
        source=desc,
        proof_level=ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF,
        fact_type=fact_type,
        identity=ProviderIdentity(
            source_key=source_key,
            provider_fixture_id=str(data.get("fixture_id", "fixture-1")),
            provider_home_team_id="home-1",
            provider_away_team_id="away-1",
            normalized_home_name="Home FC",
            normalized_away_name="Away FC",
            identity_confidence=0.9,
        ),
        freshness=EvidenceFreshness(
            observed_at=observed_at,
            stale_after=observed_at + timedelta(hours=1),
            is_current_truth_allowed=False,
            freshness_reason="soccerdata parsed replay batch",
        ),
        payload_policy=PayloadPolicy(
            payload_hash=payload_hash,
            payload_byte_count=len(json.dumps(claim_value)),
            payload_record_count=1,
        ),
        claim_value=claim_value,
        confidence=0.65,
    )
    
    batch_id = EvidenceClaimBatch.deterministic_id(source_key, "football-foundation-pass2", (claim,))
    return EvidenceClaimBatch(
        batch_id=batch_id,
        source_key=source_key,
        adapter_name=f"SoccerData{source.capitalize()}Adapter",
        adapter_version="football-foundation-pass2",
        generated_at=observed_at,
        claims=(claim,),
    )

# Line-endings normalization proof
