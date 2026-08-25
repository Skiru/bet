from collections import defaultdict
from typing import Any, Dict, List, Optional
from .contracts import NormalizedFact, NormalizedMatchSnapshot

SOURCE_PRIORITY = [
    "api-football",
    "sportdb",
    "highlightly",
    "football-data-org",
    "espn-baseline"
]

SOURCE_PRIORITY_MAP = {
    "api-football": 100,
    "sportdb": 90,
    "highlightly": 85,
    "football-data-org": 80,
    "espn-baseline": 30,
}

def _best_fact(facts: List[NormalizedFact], fact_type: str, key: str) -> Optional[NormalizedFact]:
    candidates = [f for f in facts if f.fact_type == fact_type and f.key == key]
    if not candidates:
        return None
    return sorted(candidates, key=lambda f: SOURCE_PRIORITY_MAP.get(f.source, 0), reverse=True)[0]

def _provider_ids(facts: List[NormalizedFact]) -> Dict[str, str]:
    ids: Dict[str, str] = {}
    for fact in facts:
        if fact.fact_type == "provider_mapping" and fact.provider_match_id:
            ids[fact.source] = fact.provider_match_id
    return ids

def _score_conflicts(facts: List[NormalizedFact]) -> List[Dict[str, Any]]:
    scores: Dict[str, List[NormalizedFact]] = defaultdict(list)
    for fact in facts:
        if fact.fact_type == "score" and fact.key == "full_time_score":
            val = fact.value
            if isinstance(val, dict):
                norm_str = f"{val.get('home')}-{val.get('away')}"
                scores[norm_str].append(fact)
    if len(scores) <= 1:
        return []

    conflict_dict = {}
    for norm_str, fact_list in scores.items():
        conflict_dict[norm_str] = sorted(list(set(f.source for f in fact_list)))
    return [{
        "type": "score_conflict",
        "values_by_source": conflict_dict,
        "message": f"Conflict detected on full_time_score. Values and sources: {conflict_dict}"
    }]

def get_provider_fact_counts(facts: List[NormalizedFact]) -> Dict[str, int]:
    counts = {
        "api-football": 0,
        "sportdb": 0,
        "highlightly": 0,
        "football-data-org": 0,
        "espn-baseline": 0,
    }
    for fact in facts:
        if fact.source in counts:
            counts[fact.source] += 1
    return counts

def get_normalization_diagnostics(facts: List[NormalizedFact]) -> Dict[str, Any]:
    expected_fields = {
        "api-football": ["teams", "full_time_score", "status", "kickoff_utc", "venue", "event_summary", "lineup_summary"],
        "football-data-org": ["teams", "full_time_score", "status", "kickoff_utc", "stage", "group", "referee", "competition"],
        "sportdb": ["teams", "full_time_score", "referee", "venue", "event_summary", "statistics_summary", "lineup_summary", "odds_reference_available"],
        "highlightly": ["teams", "full_time_score", "status", "venue", "statistics_summary", "lineup_summary", "event_summary"],
        "espn-baseline": ["teams", "full_time_score", "status", "kickoff_utc"]
    }

    present_fields = defaultdict(set)
    for fact in facts:
        present_fields[fact.source].add(fact.key)
        if fact.fact_type == "odds_reference" and fact.key == "odds_reference_available":
            present_fields[fact.source].add("odds_reference_available")

    diagnostics: Dict[str, Any] = {}
    for provider, expected in expected_fields.items():
        missing = []
        for exp in expected:
            if exp not in present_fields[provider]:
                missing.append(exp)
        diagnostics[provider] = {
            "missing_optional_fields": sorted(missing),
            "status": "COMPLETED_WITH_WARNINGS" if missing else "FULLY_NORMALIZED"
        }
    return diagnostics

def fuse_match_snapshot(facts: List[NormalizedFact], fixture_slug: str) -> NormalizedMatchSnapshot:
    score_fact = _best_fact(facts, "score", "full_time_score")
    if not score_fact:
        raise ValueError("No full_time_score facts available; do not use hardcoded fallback values")

    teams_fact = _best_fact(facts, "fixture_identity", "teams")
    if not teams_fact:
        raise ValueError("No teams facts available; do not use hardcoded fallback values")

    status_fact = _best_fact(facts, "match_status", "status")
    if not status_fact:
        raise ValueError("No status facts available; do not use hardcoded fallback values")

    kickoff_fact = _best_fact(facts, "kickoff", "kickoff_utc")
    if not kickoff_fact:
        raise ValueError("No kickoff_utc facts available; do not use hardcoded fallback values")

    comp_fact = _best_fact(facts, "competition", "competition")
    if not comp_fact:
        raise ValueError("No competition facts available; do not use hardcoded fallback values")

    venue_fact = _best_fact(facts, "venue", "venue")
    if not venue_fact:
        raise ValueError("No venue facts available; do not use hardcoded fallback values")

    referee_fact = _best_fact(facts, "referee", "referee")
    if not referee_fact:
        raise ValueError("No referee facts available; do not use hardcoded fallback values")

    provider_ids = _provider_ids(facts)
    conflicts = _score_conflicts(facts)

    return NormalizedMatchSnapshot(
        fixture_slug=fixture_slug,
        provider_ids=provider_ids,
        teams=teams_fact.value,
        status=status_fact.value,
        score=score_fact.value,
        kickoff_utc=kickoff_fact.value,
        competition=comp_fact.value,
        venue=venue_fact.value,
        referee=referee_fact.value,
        facts=facts,
        conflicts=conflicts,
        source_priority=SOURCE_PRIORITY,
        production_selectable=False,
        manual_authorization_required=True,
        shadow_status="SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW"
    )

def fuse_snapshot(fixture_slug: str, facts: List[NormalizedFact]) -> NormalizedMatchSnapshot:
    return fuse_match_snapshot(facts, fixture_slug)
