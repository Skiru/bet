"""Tipster source certification, robots validation, and rescue matrix tracking."""
from __future__ import annotations

import urllib.robotparser
from typing import Any
from .source_registry import SOURCES, CORE_SOURCE_IDS, RESEARCH_SOURCE_IDS, LEGACY_SOURCE_IDS, MANUAL_REVIEW_SOURCE_IDS

# Exact Enum Classifications as requested
class Classification:
    CERTIFIED_SHADOW_LIVE = "CERTIFIED_SHADOW_LIVE"
    LIVE_CANDIDATE_NEEDS_ROBOTS_TERMS = "LIVE_CANDIDATE_NEEDS_ROBOTS_TERMS"
    PUBLIC_XHR_CANDIDATE_NEEDS_NETWORK_AUDIT = "PUBLIC_XHR_CANDIDATE_NEEDS_NETWORK_AUDIT"
    STATIC_HTML_CANDIDATE_NEEDS_FIXTURE_SNAPSHOTS = "STATIC_HTML_CANDIDATE_NEEDS_FIXTURE_SNAPSHOTS"
    FIXTURE_ONLY_ROBOTS_OR_TERMS_BLOCKED = "FIXTURE_ONLY_ROBOTS_OR_TERMS_BLOCKED"
    MANUAL_REVIEW_ONLY = "MANUAL_REVIEW_ONLY"
    HARD_BLOCKED_AUTH_PRIVATE_OR_LEGAL = "HARD_BLOCKED_AUTH_PRIVATE_OR_LEGAL"
    UNKNOWN_NEEDS_DEEP_REVIEW = "UNKNOWN_NEEDS_DEEP_REVIEW"


def check_source_robots_compliance(source_id: str, default_agent: str = "skiru-bet-research-bot") -> tuple[bool | None, str]:
    """Uses urllib.robotparser to check if the source allows fetching its entrypoints.

    Returns:
        (allowed_boolean_or_none, reason_string)
    """
    policy = SOURCES.get(source_id)
    if not policy:
        return False, f"source_id_not_found:{source_id}"

    if not policy.robots_required:
        return True, "robots_not_required_by_policy"

    # Resolve robots.txt URL
    base_url = policy.base_url.rstrip("/")
    robots_url = f"{base_url}/robots.txt"
    entrypoint = policy.entrypoints[0] if policy.entrypoints else base_url

    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        can_fetch = rp.can_fetch(default_agent, entrypoint)
        return can_fetch, f"robots_read_success:can_fetch={can_fetch}"
    except Exception as e:
        # Save can_fetch as None (meaning UNKNOWN) rather than hard block
        return None, f"robots_fetch_failed_or_timeout:{str(e)}"


# Source-by-source static rescue matrix specification
STATIC_RESCUE_MATRIX: dict[str, dict[str, Any]] = {
    "zawodtyper": {
        "source_id": "zawodtyper",
        "current_registry_status": "shadow_live_candidate_public_read_xhr",
        "candidate_path": "src/bet/tipsters/zawodtyper.py",
        "why_not_rejected": "Same-origin NP_ajax.php AJAX endpoint is public, read-only, has zero stealth, zero login, zero bookmaker redirects, and represents invaluable historical Polish team sentiment.",
        "blockers": [],
        "classification": Classification.CERTIFIED_SHADOW_LIVE,
        "next_certification_steps": ["Maintain public-XHR schema coverage", "Monitor ephemeral cookie boundaries"],
        "allowed_probe_type": "clean_network_observation",
        "disallowed_methods": ["stealth", "login", "cookies from user profile", "bookmaker redirects"],
        "priority": "P0",
        "recommended_next_pass": "ZAWODTYPER_ORCHESTRATOR_PRODUCTION_HANDOFF"
    },
    "sportsgambler": {
        "source_id": "sportsgambler",
        "current_registry_status": "production_candidate_after_robots_terms_fixture_review",
        "candidate_path": "src/bet/tipsters/extractors.py",
        "why_not_rejected": "Excellent narrative coverage of team lineups and injury sentiment. HTML structure is clean and static.",
        "blockers": ["Requires robots.txt and terms of service review"],
        "classification": Classification.LIVE_CANDIDATE_NEEDS_ROBOTS_TERMS,
        "next_certification_steps": ["Verify robots.txt", "Verify Terms of Service", "Fixture mapping validation"],
        "allowed_probe_type": "static_http_head_get",
        "disallowed_methods": ["stealth", "login", "cookies from user profile", "bookmaker redirects"],
        "priority": "P1",
        "recommended_next_pass": "SPORTSGAMBLER_STATIC_PREVIEW_CERTIFICATION"
    },
    "forebet": {
        "source_id": "forebet",
        "current_registry_status": "fixture_snapshot_only_manual_review_no_live_fetch",
        "candidate_path": "src/bet/tipsters/extractors.py",
        "why_not_rejected": "Highly structured AI prediction model. Even if live fetch is blocked, offline parsing of saved snapshots is highly valuable and perfectly legal.",
        "blockers": ["Live fetch robots.txt restrictions"],
        "classification": Classification.FIXTURE_ONLY_ROBOTS_OR_TERMS_BLOCKED,
        "next_certification_steps": ["Verify fixture folder snapshot pipelines", "Maintain forebet_table parser strategy"],
        "allowed_probe_type": "fixture_snapshot",
        "disallowed_methods": ["stealth", "login", "cookies from user profile", "bookmaker redirects"],
        "priority": "P1",
        "recommended_next_pass": "FOREBET_PREDICTZ_FIXTURE_SNAPSHOT_MAINTENANCE"
    },
    "predictz": {
        "source_id": "predictz",
        "current_registry_status": "fixture_snapshot_only_manual_review_no_live_fetch",
        "candidate_path": "src/bet/tipsters/extractors.py",
        "why_not_rejected": "Provides basic match scores and form-trends that help cross-check team identities and baseline sentiment without live-fetch pressure.",
        "blockers": ["Live fetch robots.txt restrictions"],
        "classification": Classification.FIXTURE_ONLY_ROBOTS_OR_TERMS_BLOCKED,
        "next_certification_steps": ["Verify fixture folder snapshot pipelines", "Maintain predictz_fixture_table parser strategy"],
        "allowed_probe_type": "fixture_snapshot",
        "disallowed_methods": ["stealth", "login", "cookies from user profile", "bookmaker redirects"],
        "priority": "P1",
        "recommended_next_pass": "FOREBET_PREDICTZ_FIXTURE_SNAPSHOT_MAINTENANCE"
    },
    "windrawwin": {
        "source_id": "windrawwin",
        "current_registry_status": "production_candidate_after_robots_terms_fixture_review",
        "candidate_path": "src/bet/tipsters/extractors.py",
        "why_not_rejected": "Clean static HTML structure. Covers unique markets like corners and BTTS statistics which are invaluable for S4 market sanity.",
        "blockers": ["Requires robots.txt and terms of service review"],
        "classification": Classification.LIVE_CANDIDATE_NEEDS_ROBOTS_TERMS,
        "next_certification_steps": ["Verify robots.txt", "Verify Terms of Service", "Verify league prediction tables parser"],
        "allowed_probe_type": "static_http_head_get",
        "disallowed_methods": ["stealth", "login", "cookies from user profile", "bookmaker redirects"],
        "priority": "P1",
        "recommended_next_pass": "WINDRAWWIN_STATIC_TABLE_CERTIFICATION"
    },
    "feedinco": {
        "source_id": "feedinco",
        "current_registry_status": "shadow_candidate_high_noise",
        "candidate_path": "src/bet/tipsters/extractors.py",
        "why_not_rejected": "Excellent multi-sport coverage (cricket, tennis, eSports) which can provide contextual agreement signals if affiliate noise is aggressively filtered.",
        "blockers": ["High affiliate noise surface", "Requires aggressive date validation"],
        "classification": Classification.STATIC_HTML_CANDIDATE_NEEDS_FIXTURE_SNAPSHOTS,
        "next_certification_steps": ["Implement noise filters", "Test with local HTML fixture snapshots first"],
        "allowed_probe_type": "fixture_snapshot",
        "disallowed_methods": ["stealth", "login", "cookies from user profile", "bookmaker redirects"],
        "priority": "P2",
        "recommended_next_pass": "FEEDINCO_SHADOW_NOISE_FILTER_AUDIT"
    },
    "bettingclosed": {
        "source_id": "bettingclosed",
        "current_registry_status": "shadow_candidate_requires_js_loading_review",
        "candidate_path": "src/bet/tipsters/extractors.py",
        "why_not_rejected": "Covers a very wide selection of obscure global football leagues. JS-loading structure needs public network/XHR audit to see if static fallback can be extracted safely.",
        "blockers": ["JS rendering required on some pages", "Terms of service ambiguity"],
        "classification": Classification.PUBLIC_XHR_CANDIDATE_NEEDS_NETWORK_AUDIT,
        "next_certification_steps": ["Perform clean network observation", "Check if data is present in static DOM"],
        "allowed_probe_type": "clean_network_observation",
        "disallowed_methods": ["stealth", "login", "cookies from user profile", "bookmaker redirects"],
        "priority": "P2",
        "recommended_next_pass": "BETTINGCLOSED_JS_PUBLIC_AUDIT"
    },
    "typersi": {
        "source_id": "typersi",
        "current_registry_status": "legacy_candidate_requires_compliance_certification",
        "candidate_path": "src/bet/tipsters/legacy_bridge.py",
        "why_not_rejected": "One of the most popular Polish community tipster sites. Like ZawodTyper, it contains high-value Polish football opinions, requiring public read-only XHR/HTML compliance audit.",
        "blockers": ["Dynamic DOM structure", "Legacy extraction heuristics"],
        "classification": Classification.PUBLIC_XHR_CANDIDATE_NEEDS_NETWORK_AUDIT,
        "next_certification_steps": ["Audit network traffic for public API", "Verify robots.txt compliance"],
        "allowed_probe_type": "clean_network_observation",
        "disallowed_methods": ["stealth", "login", "cookies from user profile", "bookmaker redirects"],
        "priority": "P1",
        "recommended_next_pass": "TYPERSI_PUBLIC_READ_AUDIT"
    },
    "betmines": {
        "source_id": "betmines",
        "current_registry_status": "research_only_dynamic_auth_surfaces",
        "candidate_path": "src/bet/tipsters/extractors.py",
        "why_not_rejected": "Highly dynamic UI but exposes extremely solid AI-driven probabilities. Good for research or manual sentiment extraction.",
        "blockers": ["Dynamic JS loading", "Highly restricted robots.txt and login prompts on advanced pages"],
        "classification": Classification.MANUAL_REVIEW_ONLY,
        "next_certification_steps": ["Maintain manual review path only", "Review API terms"],
        "allowed_probe_type": "none",
        "disallowed_methods": ["stealth", "login", "cookies from user profile", "bookmaker redirects"],
        "priority": "P3",
        "recommended_next_pass": "MANUAL_REVIEW_ONLY"
    },
    "sportytrader": {
        "source_id": "sportytrader",
        "current_registry_status": "research_only_next_phase",
        "candidate_path": "src/bet/tipsters/extractors.py",
        "why_not_rejected": "Excellent preview texts and expert analysis. Good for manual qualitative sentiment.",
        "blockers": ["Affiliate redirects", "Large page weight and noise"],
        "classification": Classification.MANUAL_REVIEW_ONLY,
        "next_certification_steps": ["Evaluate static parsing of preview articles"],
        "allowed_probe_type": "static_http_head_get",
        "disallowed_methods": ["stealth", "login", "cookies from user profile", "bookmaker redirects"],
        "priority": "P2",
        "recommended_next_pass": "SPORTSGAMBLER_STATIC_PREVIEW_CERTIFICATION"
    },
    "pickswise": {
        "source_id": "pickswise",
        "current_registry_status": "legacy_manual_review_dynamic_affiliate_sensitive",
        "candidate_path": "src/bet/tipsters/extractors.py",
        "why_not_rejected": "Major US sports expert brand. Highly valuable sentiment, but heavily dynamic affiliate-sponsored environment requires strictly manual review.",
        "blockers": ["Dynamic DOM loading", "Heavy bookmaker redirect banners"],
        "classification": Classification.MANUAL_REVIEW_ONLY,
        "next_certification_steps": ["Retain manual review only"],
        "allowed_probe_type": "none",
        "disallowed_methods": ["stealth", "login", "cookies from user profile", "bookmaker redirects"],
        "priority": "P3",
        "recommended_next_pass": "PICKSWISE_OLBG_BETTINGEXPERT_MANUAL_REVIEW"
    },
    "betideas": {
        "source_id": "betideas",
        "current_registry_status": "legacy_manual_review_dynamic_affiliate_sensitive",
        "candidate_path": "src/bet/tipsters/extractors.py",
        "why_not_rejected": "Valuable match preview claims but environment is dynamic and contains heavy affiliate marketing elements.",
        "blockers": ["Dynamic listings", "Affiliate links and redirects"],
        "classification": Classification.MANUAL_REVIEW_ONLY,
        "next_certification_steps": ["Retain manual review only"],
        "allowed_probe_type": "none",
        "disallowed_methods": ["stealth", "login", "cookies from user profile", "bookmaker redirects"],
        "priority": "P3",
        "recommended_next_pass": "PICKSWISE_OLBG_BETTINGEXPERT_MANUAL_REVIEW"
    },
    "olbg": {
        "source_id": "olbg",
        "current_registry_status": "manual_review_only",
        "candidate_path": "src/bet/tipsters/extractors.py",
        "why_not_rejected": "Community tipster rankings have huge statistical sample sizes, but legal terms-of-use and dynamic JS require safe manual review/curation.",
        "blockers": ["Extremely restrictive robots.txt", "Advanced path protections"],
        "classification": Classification.MANUAL_REVIEW_ONLY,
        "next_certification_steps": ["Retain manual review only"],
        "allowed_probe_type": "none",
        "disallowed_methods": ["stealth", "login", "cookies from user profile", "bookmaker redirects"],
        "priority": "P3",
        "recommended_next_pass": "PICKSWISE_OLBG_BETTINGEXPERT_MANUAL_REVIEW"
    },
    "bettingexpert": {
        "source_id": "bettingexpert",
        "current_registry_status": "manual_review_only",
        "candidate_path": "src/bet/tipsters/extractors.py",
        "why_not_rejected": "One of the most famous community tipping sites. Highly restrictive environment but superb historical data for manual sentiment research.",
        "blockers": ["Dynamic frontend hydration", "Aggressive Cloudflare/anti-bot protection", "Highly restrictive Terms of Service"],
        "classification": Classification.MANUAL_REVIEW_ONLY,
        "next_certification_steps": ["Retain manual review only"],
        "allowed_probe_type": "none",
        "disallowed_methods": ["stealth", "login", "cookies from user profile", "bookmaker redirects"],
        "priority": "P3",
        "recommended_next_pass": "PICKSWISE_OLBG_BETTINGEXPERT_MANUAL_REVIEW"
    }
}


def build_source_certification_matrix(run_robots_probe: bool = False) -> list[dict[str, Any]]:
    """Builds a complete, auditable list of all tipster sources with their current

    classification, candidate paths, and next certification actions.
    """
    matrix = []
    for source_id, spec in STATIC_RESCUE_MATRIX.items():
        entry = dict(spec)
        if run_robots_probe:
            allowed, detail = check_source_robots_compliance(source_id)
            entry["robots_allowed_probe"] = allowed
            entry["robots_probe_detail"] = detail
            if allowed is None:
                # If robots cannot be fetched, do not hard block, mark as unknown review
                entry["classification"] = Classification.UNKNOWN_NEEDS_DEEP_REVIEW
        else:
            entry["robots_allowed_probe"] = None
            entry["robots_probe_detail"] = "probe_not_executed_to_prevent_network_usage"
        matrix.append(entry)
    return sorted(matrix, key=lambda x: (x["priority"], x["source_id"]))
