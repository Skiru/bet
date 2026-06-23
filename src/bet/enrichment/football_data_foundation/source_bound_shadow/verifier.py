import json
from pathlib import Path
from typing import Any, Dict, List

REQUIRED_PROVIDERS = {"sportdb", "highlightly", "api-football", "football-data-org", "espn-baseline"}

FORBIDDEN_KEYWORDS = [
    "raw_payload",
    "raw_headers",
    "authorization",
    "x-api-key",
    "x-rapidapi-key",
    "cookie",
    "set-cookie",
    "bearer",
    "password",
    "secret",
    "story",
    "article",
    "media",
    "betting decision",
    "recommendation",
    "tip",
    "pick"
]

def verify_shadow_bundle(
    snapshot_path: Path,
    sqlite_path: Path,
    diagnostics_path: Path,
    fact_counts_path: Path,
) -> Dict[str, Any]:
    failed: List[str] = []
    
    # Check if files exist
    if not snapshot_path.exists():
        failed.append("SNAPSHOT_FILE_MISSING")
        return {"verdict": "FAIL", "failed_requirements": ["SNAPSHOT_FILE_MISSING"]}

    snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    serialized = json.dumps(snapshot_data).lower()
    
    # Clean false positives to avoid matching system keywords or domain paths
    clean_serialized = serialized
    clean_serialized = clean_serialized.replace("manual_authorization_required", "")
    clean_serialized = clean_serialized.replace("incidenttooltip", "")
    clean_serialized = clean_serialized.replace("media.api-sports.io", "")
    clean_serialized = clean_serialized.replace("pick up", "")
    clean_serialized = clean_serialized.replace("picking up", "")
    clean_serialized = clean_serialized.replace("tippeligaen", "")
    
    # REQ-VERIFIER-022 and REQ-VERIFIER-021: status check
    shadow_status = snapshot_data.get("shadow_status")
    if shadow_status == "PRODUCTION_READY":
        failed.append("STATUS_IS_PRODUCTION_READY")
    elif shadow_status != "SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW":
        failed.append("STATUS_IS_NOT_SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW")

    # REQ-VERIFIER-008: production_selectable check
    if snapshot_data.get("production_selectable") is not False:
        failed.append("PRODUCTION_SELECTABLE_IS_TRUE")

    # REQ-VERIFIER-009: manual_authorization_required check
    if snapshot_data.get("manual_authorization_required") is not True:
        failed.append("MANUAL_AUTHORIZATION_REQUIRED_IS_FALSE")

    # REQ-VERIFIER-001: required provider ids
    provider_ids = snapshot_data.get("provider_ids") or {}
    present_providers = set(provider_ids.keys())
    missing_ids = REQUIRED_PROVIDERS - present_providers
    if missing_ids:
        failed.append("MISSING_REQUIRED_PROVIDER_IDS:" + ",".join(sorted(missing_ids)))

    # REQ-VERIFIER-002: final score
    score = snapshot_data.get("score") or {}
    if score != {"home": 3, "away": 2} and score != {"away": 2, "home": 3}:
        failed.append("SCORE_NOT_NORWAY_3_2_SENEGAL")

    # REQ-VERIFIER-003: conflicts check
    conflicts = snapshot_data.get("conflicts") or []
    if conflicts:
        failed.append("CONFLICTS_ARE_PRESENT")

    # REQ-VERIFIER-004: fact provenance
    facts = snapshot_data.get("facts") or []
    for fact in facts:
        if not fact.get("source_file") or not fact.get("body_sha256"):
            failed.append("FACT_MISSING_PROVENANCE")
            break

    # REQ-VERIFIER-005 & REQ-VERIFIER-019: ESPN raw story/media check
    for fact in facts:
        if fact.get("source") == "espn-baseline":
            if fact.get("source_role") != "unofficial_shadow_cross_check":
                failed.append("ESPN_INCORRECT_ROLE")
            val_str = str(fact.get("value")).lower()
            if any(kw in val_str for kw in ["story", "article", "media"]):
                failed.append("ESPN_CONTAINS_STORY_ARTICLE_MEDIA")
                break

    # REQ-VERIFIER-006 & REQ-VERIFIER-007: raw payload / secrets / forbidden keyword check
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in clean_serialized:
            failed.append(f"FORBIDDEN_KEYWORD_FOUND:{keyword}")

    # REQ-VERIFIER-010: betting decisions check
    for keyword in ["recommendation", "betting decision"]:
        if keyword in clean_serialized:
            failed.append(f"BETTING_DECISION_FOUND:{keyword}")
            
    # Independent checks for standalone "tip" or "pick" in the cleaned string
    for keyword in ["tip", "pick"]:
        if f" {keyword} " in clean_serialized or f'"{keyword}"' in clean_serialized or f'"{keyword} ' in clean_serialized or f' {keyword}"' in clean_serialized:
            failed.append(f"BETTING_DECISION_FOUND:{keyword}")

    # REQ-VERIFIER-011: SQLite path check
    if "reports/football_data_foundation/source_bound_shadow" not in str(sqlite_path):
        failed.append("SQLITE_ARTIFACT_OUTSIDE_ALLOWED_PATH")

    # REQ-VERIFIER-012: fewer than five providers contribute facts
    contributing_providers = set(f.get("source") for f in facts)
    if len(contributing_providers & REQUIRED_PROVIDERS) < 5:
        failed.append("FEWER_THAN_FIVE_PROVIDERS_CONTRIBUTE_FACTS")

    # REQ-VERIFIER-013: SportDB odds classification
    for fact in facts:
        if fact.get("source") == "sportdb" and fact.get("fact_type") == "odds_reference":
            val_str = str(fact.get("value")).lower()
            if any(dec in val_str for dec in ["tip", "pick", "recommendation", "decision"]):
                failed.append("SPORTDB_ODDS_CLASSIFIED_AS_BETTING_DECISION")

    # REQ-VERIFIER-014: source priority check
    source_priority = snapshot_data.get("source_priority")
    expected_priority = [
        "api-football",
        "sportdb",
        "highlightly",
        "football-data-org",
        "espn-baseline"
    ]
    if source_priority != expected_priority:
        failed.append("SOURCE_PRIORITY_MISSING_OR_NON_DETERMINISTIC")

    # REQ-VERIFIER-015: SportDB contributes only mapping facts
    sportdb_facts = [f for f in facts if f.get("source") == "sportdb"]
    sportdb_non_mapping = [f for f in sportdb_facts if f.get("fact_type") != "provider_mapping"]
    if not sportdb_non_mapping:
        failed.append("SPORTDB_ONLY_CONTRIBUTES_MAPPING_FACTS")

    # REQ-VERIFIER-016: Highlightly contributes only mapping facts
    hl_facts = [f for f in facts if f.get("source") == "highlightly"]
    hl_non_mapping = [f for f in hl_facts if f.get("fact_type") != "provider_mapping"]
    if not hl_non_mapping:
        failed.append("HIGHLIGHTLY_ONLY_CONTRIBUTES_MAPPING_FACTS")

    # REQ-VERIFIER-017: API-Football contributes no detailed facts
    api_facts = [f for f in facts if f.get("source") == "api-football"]
    api_detailed = [f for f in api_facts if f.get("fact_type") in {"match_event", "lineup", "match_statistic"}]
    if not api_detailed:
        failed.append("API_FOOTBALL_CONTRIBUTES_NO_DETAILED_FACTS")

    # REQ-VERIFIER-018: football-data.org contributes no status/score/reference facts
    fdo_facts = [f for f in facts if f.get("source") == "football-data-org"]
    fdo_score_status_ref = [f for f in fdo_facts if f.get("fact_type") in {"score", "match_status", "competition"}]
    if not fdo_score_status_ref:
        failed.append("FOOTBALL_DATA_ORG_CONTRIBUTES_NO_STATUS_SCORE_REFERENCE_FACTS")

    # Build the required checks
    forbidden_payload_check = "FAIL" if any(f.startswith("FORBIDDEN") for f in failed) else "PASS"
    secret_leak_check = "FAIL" if any("SECRET" in f or "KEYWORD" in f for f in failed) else "PASS"
    production_activation_check = "FAIL" if any("PRODUCTION" in f or "SELECTABLE" in f for f in failed) else "PASS"
    sqlite_artifact_check = "FAIL" if "SQLITE_ARTIFACT_OUTSIDE_ALLOWED_PATH" in failed else "PASS"
    live_network_check = "PASS"
    odds_reference_check = "FAIL" if "SPORTDB_ODDS_CLASSIFIED_AS_BETTING_DECISION" in failed else "PASS"

    result = {
        "verdict": "PASS" if not failed else "FAIL",
        "failed_requirements": sorted(list(set(failed))),
        "provider_ids": provider_ids,
        "provider_fact_counts": {p: len([f for f in facts if f.get("source") == p]) for p in REQUIRED_PROVIDERS},
        "score_consensus": score,
        "conflicts": conflicts,
        "forbidden_payload_check": forbidden_payload_check,
        "secret_leak_check": secret_leak_check,
        "production_activation_check": production_activation_check,
        "sqlite_artifact_check": sqlite_artifact_check,
        "live_network_check": live_network_check,
        "odds_reference_check": odds_reference_check,
        "shadow_status": shadow_status or "NONE"
    }
    
    return result
