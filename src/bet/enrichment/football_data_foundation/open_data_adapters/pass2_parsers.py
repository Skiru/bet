from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
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
)


def parse_statsbomb_tree(root: Path) -> EvidenceClaimBatch:
    comp_path = root / "competitions.json"
    comp_data = []
    if comp_path.exists():
        comp_data = json.loads(comp_path.read_text(encoding="utf-8"))
    
    events_dir = root / "events"
    events_files = list(events_dir.glob("*.json")) if events_dir.exists() else []
    
    event_count = 0
    shot_count = 0
    xg_sum = 0.0
    
    for f in events_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            event_count += len(data)
            for ev in data:
                # check both nested statsbomb format and simplified layout
                type_name = ""
                if isinstance(ev.get("type"), dict):
                    type_name = ev["type"].get("name", "")
                elif isinstance(ev.get("type"), str):
                    type_name = ev["type"]

                if type_name == "Shot":
                    shot_count += 1
                    xg = 0.0
                    if "shot" in ev and isinstance(ev["shot"], dict) and "statsbomb_xg" in ev["shot"]:
                        xg = float(ev["shot"]["statsbomb_xg"])
                    elif "xg" in ev:
                        xg = float(ev["xg"])
                    xg_sum += xg
        except Exception:
            pass
            
    lineups_dir = root / "lineups"
    lineups_count = 0
    if lineups_dir.exists():
        for f in lineups_dir.glob("*.json"):
            try:
                lineups_count += len(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
                
    three_sixty_dir = root / "three-sixty"
    three_sixty_frame_count = 0
    if three_sixty_dir.exists():
        for f in three_sixty_dir.glob("*.json"):
            try:
                three_sixty_frame_count += len(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass

    source = SourceDescriptor(
        source_key="statsbomb-open-data",
        display_name="StatsBomb Open Data",
        role=SourceRole.HISTORICAL_DEEP,
        requires_credentials=False,
        supports_live=False,
        supports_historical=True,
        supports_reference=True,
        supports_replay=True,
        allowed_proof_levels=(ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,),
    )
    
    claim_value = {
        "competition_count": len(comp_data),
        "event_count": event_count,
        "shot_count": shot_count,
        "xg_sum": round(xg_sum, 4),
        "lineups_count": lineups_count,
        "three_sixty_frame_count": three_sixty_frame_count,
    }
    
    observed_at = datetime.now(UTC)
    
    claim = EvidenceClaim(
        source=source,
        proof_level=ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,
        fact_type=FactType.MATCH_EVENT,
        identity=ProviderIdentity(source_key="statsbomb-open-data"),
        freshness=EvidenceFreshness(
            observed_at=observed_at,
            is_current_truth_allowed=False,
            freshness_reason="StatsBomb open data parsed local batch",
        ),
        payload_policy=PayloadPolicy(),
        claim_value=claim_value,
        confidence=0.8,
    )
    
    batch_id = EvidenceClaimBatch.deterministic_id("statsbomb-open-data", "football-foundation-pass2", (claim,))
    return EvidenceClaimBatch(
        batch_id=batch_id,
        source_key="statsbomb-open-data",
        adapter_name="StatsBombOpenDataAdapter",
        adapter_version="football-foundation-pass2",
        generated_at=observed_at,
        claims=(claim,),
    )


def parse_openfootball_text(path: Path) -> EvidenceClaimBatch:
    lines = []
    if path.exists():
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
        
    fixtures = []
    for line in lines:
        if ";" in line:
            parts = line.split(";")
            fixtures.append({
                "raw_line": line,
                "parts_count": len(parts),
            })
            
    source = SourceDescriptor(
        source_key="openfootball",
        display_name="OpenFootball",
        role=SourceRole.REFERENCE_IDENTITY,
        requires_credentials=False,
        supports_live=False,
        supports_historical=True,
        supports_reference=True,
        supports_replay=True,
        allowed_proof_levels=(ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,),
        forbidden_fact_types=(FactType.XG, FactType.SHOT, FactType.LINEUP, FactType.MATCH_STATISTIC, FactType.THREE_SIXTY_FRAME),
    )
    
    claim_value = {
        "line_count": len(lines),
        "fixture_count": len(fixtures),
    }
    
    observed_at = datetime.now(UTC)
    
    claim = EvidenceClaim(
        source=source,
        proof_level=ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,
        fact_type=FactType.REFERENCE_RESULT,
        identity=ProviderIdentity(source_key="openfootball"),
        freshness=EvidenceFreshness(
            observed_at=observed_at,
            is_current_truth_allowed=False,
            freshness_reason="OpenFootball text file parse",
        ),
        payload_policy=PayloadPolicy(),
        claim_value=claim_value,
        confidence=0.75,
    )
    
    batch_id = EvidenceClaimBatch.deterministic_id("openfootball", "football-foundation-pass2", (claim,))
    return EvidenceClaimBatch(
        batch_id=batch_id,
        source_key="openfootball",
        adapter_name="OpenFootballAdapter",
        adapter_version="football-foundation-pass2",
        generated_at=observed_at,
        claims=(claim,),
    )


def parse_kaggle_european_soccer_csv(path: Path) -> EvidenceClaimBatch:
    rows = []
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
                
    source = SourceDescriptor(
        source_key="kaggle-european-soccer",
        display_name="Kaggle European Soccer Database",
        role=SourceRole.HISTORICAL_DEEP,
        requires_credentials=False,
        supports_live=False,
        supports_historical=True,
        supports_reference=True,
        supports_replay=True,
        allowed_proof_levels=(ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,),
    )
    
    claim_value = {
        "record_count": len(rows),
        "temporal_decay_required": True,
    }
    
    observed_at = datetime.now(UTC)
    
    claim = EvidenceClaim(
        source=source,
        proof_level=ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,
        fact_type=FactType.HISTORICAL_PRIOR,
        identity=ProviderIdentity(source_key="kaggle-european-soccer"),
        freshness=EvidenceFreshness(
            observed_at=observed_at,
            is_current_truth_allowed=False,
            freshness_reason="Kaggle CSV parsed",
        ),
        payload_policy=PayloadPolicy(),
        claim_value=claim_value,
        confidence=0.7,
    )
    
    batch_id = EvidenceClaimBatch.deterministic_id("kaggle-european-soccer", "football-foundation-pass2", (claim,))
    return EvidenceClaimBatch(
        batch_id=batch_id,
        source_key="kaggle-european-soccer",
        adapter_name="KaggleEuropeanSoccerAdapter",
        adapter_version="football-foundation-pass2",
        generated_at=observed_at,
        claims=(claim,),
    )

# Line-endings normalization proof
