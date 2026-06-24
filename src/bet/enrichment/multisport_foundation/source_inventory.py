from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

TARGET_SPORTS: tuple[str, ...] = ('basketball', 'volleyball', 'hockey', 'tennis', 'cs2', 'dota2', 'valorant')
FOOTBALL_ERA_SOURCE_KEYS: tuple[str, ...] = ('sportdb', 'highlightly', 'api-football', 'api-sports-family', 'football-data-org', 'thesportsdb', 'espn-baseline', 'statsbomb-open-data', 'statsbombpy', 'openfootball', 'kaggle-european-soccer', 'soccerdata-clubelo', 'soccerdata-espn', 'soccerdata-fbref', 'soccerdata-fivethirtyeight', 'soccerdata-matchhistory', 'soccerdata-sofascore', 'soccerdata-sofifa', 'soccerdata-understat', 'soccerdata-whoscored', 'fotmob-probe', 'sofascore-rich-probe', 'scraperfc-sofascore-bridge', 'pandascore', 'liquipedia-reference')
DIRECT_DECISIONS = {"transfer_direct"}
PROBE_DECISIONS = {"deferred_probe_only", "blocked_terms_or_access"}
_SOURCE_JSON = r"""
[
  {
    "allowed_proof_levels": [
      "real_live_http_proof",
      "real_replay_corpus_proof",
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://sportdb.dev/",
    "football_role": "Football REST/MCP shadow provider evaluated as strategic multisport pattern.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "marking_mapped_when_target_participants_are_absent"
    ],
    "notes": "Provider-bound corpus only from sanitized REST/MCP proof envelopes; no fake mapping for generic result lists.",
    "required_env_keys": [
      "SPORTDB_API_KEY"
    ],
    "source_family": "direct_freemium_live_current",
    "source_key": "sportdb",
    "target_sport_applicability": "Direct for documented basketball, hockey and tennis; volleyball requires explicit proof before use.",
    "target_sports": [
      "basketball",
      "hockey",
      "tennis"
    ],
    "terms_or_access_review_required": true,
    "transfer_decision": "transfer_direct"
  },
  {
    "allowed_proof_levels": [
      "real_live_http_proof",
      "real_replay_corpus_proof",
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://highlightly.net/sport-api/",
    "football_role": "Accepted football shadow provider pattern for limited form/H2H/detailed metrics scope.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "using_odds_predictions_for_betting_decisions",
      "claiming_match_mapping_from_unrelated_lists"
    ],
    "notes": "All Sports API is useful cross-sport source, but Pass B stores source-bound sanitized corpus only.",
    "required_env_keys": [
      "HIGHLIGHTLY_API_KEY"
    ],
    "source_family": "direct_freemium_live_current",
    "source_key": "highlightly",
    "target_sport_applicability": "Direct for basketball, hockey and volleyball where docs/API proof exists; tennis not direct without explicit docs proof.",
    "target_sports": [
      "basketball",
      "volleyball",
      "hockey"
    ],
    "terms_or_access_review_required": true,
    "transfer_decision": "transfer_direct"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://www.api-football.com/documentation-v3",
    "football_role": "Football-specific API-Sports baseline/reference from football enrichment.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable"
    ],
    "notes": "Do not use football endpoints as generic proof for non-football sports.",
    "required_env_keys": [
      "API_FOOTBALL_KEY"
    ],
    "source_family": "direct_freemium_live_current",
    "source_key": "api-football",
    "target_sport_applicability": "Football-only reference; use only as historical pattern for API-Sports family contracts.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "real_live_http_proof",
      "real_replay_corpus_proof",
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://api-sports.io/",
    "football_role": "Provider family pattern derived from API-Football/API-Sports football work.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "generic_api_sports_success_without_sport_specific_endpoint_proof"
    ],
    "notes": "Each sport must prove endpoint family, env route, and sanitized response separately.",
    "required_env_keys": [
      "API_BASKETBALL_KEY",
      "API_VOLLEYBALL_KEY",
      "API_HOCKEY_KEY",
      "API_TENNIS_KEY",
      "API_SPORTS_KEY"
    ],
    "source_family": "direct_freemium_live_current",
    "source_key": "api-sports-family",
    "target_sport_applicability": "Direct for basketball, volleyball, hockey and tennis only with sport-specific docs/env proof.",
    "target_sports": [
      "basketball",
      "volleyball",
      "hockey",
      "tennis"
    ],
    "terms_or_access_review_required": true,
    "transfer_decision": "transfer_direct"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://www.football-data.org/documentation/quickstart",
    "football_role": "Football-only standings/current discovery shadow reference.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable"
    ],
    "notes": "Do not make it a blocker for multisport; no non-football source-bound claims.",
    "required_env_keys": [
      "FOOTBALL_DATA_API_KEY"
    ],
    "source_family": "direct_freemium_live_current",
    "source_key": "football-data-org",
    "target_sport_applicability": "Not applicable directly to target sports; keep as contract pattern only.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "real_live_http_proof",
      "real_replay_corpus_proof",
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://www.thesportsdb.com/free_sports_api",
    "football_role": "Crowd-sourced sports reference/fallback source used for cross-reference style checks.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "sole_activation_ready_current_truth"
    ],
    "notes": "Useful for identity/cross-ref corpus; source-bound ready requires mapped event/participants and cross-check evidence.",
    "required_env_keys": [
      "THESPORTSDB_API_KEY",
      "THESPORTSDB_KEY"
    ],
    "source_family": "direct_freemium_live_current",
    "source_key": "thesportsdb",
    "target_sport_applicability": "Reference transfer for team sports and tennis, not sole current truth.",
    "target_sports": [
      "basketball",
      "volleyball",
      "hockey",
      "tennis"
    ],
    "terms_or_access_review_required": true,
    "transfer_decision": "transfer_as_pattern"
  },
  {
    "allowed_proof_levels": [
      "real_live_http_proof",
      "real_replay_corpus_proof",
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://site.api.espn.com/apis/site/v2/sports/",
    "football_role": "Football baseline/current schedule pattern from public ESPN endpoints.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "scraping_articles_media_story_text",
      "undocumented_endpoint_claim_without_sanitized_proof"
    ],
    "notes": "Observation/reference only after endpoint and response schema are captured and sanitized.",
    "required_env_keys": [],
    "source_family": "direct_freemium_live_current",
    "source_key": "espn-baseline",
    "target_sport_applicability": "Transfer as sanitized schedule/reference pattern where endpoint proof is explicit; no media/story text.",
    "target_sports": [
      "basketball",
      "hockey",
      "tennis"
    ],
    "terms_or_access_review_required": true,
    "transfer_decision": "transfer_as_pattern"
  },
  {
    "allowed_proof_levels": [
      "real_open_data_proof",
      "docs_capability_only"
    ],
    "docs_url": "https://github.com/statsbomb/open-data",
    "football_role": "Football open event data/reference dataset.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable"
    ],
    "notes": "Keep in inventory to avoid silent drop; never block target sports.",
    "required_env_keys": [],
    "source_family": "open_reference_replay",
    "source_key": "statsbomb-open-data",
    "target_sport_applicability": "Football-only reference; useful as open-data adapter pattern but not direct multisport source.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "real_open_data_proof",
      "docs_capability_only"
    ],
    "docs_url": "https://github.com/statsbomb/statsbombpy",
    "football_role": "Python bridge to StatsBomb open/proprietary football data.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable"
    ],
    "notes": "Do not introduce dependency in Pass B multisport runtime.",
    "required_env_keys": [],
    "source_family": "open_reference_replay",
    "source_key": "statsbombpy",
    "target_sport_applicability": "Football-only library pattern for replay adapters.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "real_open_data_proof",
      "docs_capability_only"
    ],
    "docs_url": "https://openfootball.github.io/",
    "football_role": "Open public-domain football datasets and schema.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable"
    ],
    "notes": "No direct target-sport source-bound use.",
    "required_env_keys": [],
    "source_family": "open_reference_replay",
    "source_key": "openfootball",
    "target_sport_applicability": "Football-only reference; transfer schema/replay idea only.",
    "target_sports": [],
    "terms_or_access_review_required": false,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "real_open_data_proof",
      "docs_capability_only"
    ],
    "docs_url": "https://www.kaggle.com/datasets/hugomathien/soccer",
    "football_role": "Football historical dataset bridge/reference.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable",
      "assuming_kaggle_dataset_license_allows_production_use"
    ],
    "notes": "Requires dataset/license review if ever used beyond reference.",
    "required_env_keys": [],
    "source_family": "open_reference_replay",
    "source_key": "kaggle-european-soccer",
    "target_sport_applicability": "Football-only historical pattern; not target sport data.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://soccerdata.readthedocs.io/",
    "football_role": "Football-only soccerdata adapter from football enrichment source inventory.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable",
      "live_scraping_in_pass_b",
      "production_dependency_without_site_terms_review"
    ],
    "notes": "Accounted for explicitly; does not block multisport Pass B.",
    "required_env_keys": [],
    "source_family": "soccerdata_library_adapter",
    "source_key": "soccerdata-clubelo",
    "target_sport_applicability": "Football-only library adapter; no direct target sport applicability.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://soccerdata.readthedocs.io/",
    "football_role": "Football-only soccerdata adapter from football enrichment source inventory.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable",
      "live_scraping_in_pass_b",
      "production_dependency_without_site_terms_review"
    ],
    "notes": "Accounted for explicitly; does not block multisport Pass B.",
    "required_env_keys": [],
    "source_family": "soccerdata_library_adapter",
    "source_key": "soccerdata-espn",
    "target_sport_applicability": "Football-only library adapter; no direct target sport applicability.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://soccerdata.readthedocs.io/",
    "football_role": "Football-only soccerdata adapter from football enrichment source inventory.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable",
      "live_scraping_in_pass_b",
      "production_dependency_without_site_terms_review"
    ],
    "notes": "Accounted for explicitly; does not block multisport Pass B.",
    "required_env_keys": [],
    "source_family": "soccerdata_library_adapter",
    "source_key": "soccerdata-fbref",
    "target_sport_applicability": "Football-only library adapter; no direct target sport applicability.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://soccerdata.readthedocs.io/",
    "football_role": "Football-only soccerdata adapter from football enrichment source inventory.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable",
      "live_scraping_in_pass_b",
      "production_dependency_without_site_terms_review"
    ],
    "notes": "Accounted for explicitly; does not block multisport Pass B.",
    "required_env_keys": [],
    "source_family": "soccerdata_library_adapter",
    "source_key": "soccerdata-fivethirtyeight",
    "target_sport_applicability": "Football-only library adapter; no direct target sport applicability.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://soccerdata.readthedocs.io/",
    "football_role": "Football-only soccerdata adapter from football enrichment source inventory.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable",
      "live_scraping_in_pass_b",
      "production_dependency_without_site_terms_review"
    ],
    "notes": "Accounted for explicitly; does not block multisport Pass B.",
    "required_env_keys": [],
    "source_family": "soccerdata_library_adapter",
    "source_key": "soccerdata-matchhistory",
    "target_sport_applicability": "Football-only library adapter; no direct target sport applicability.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://soccerdata.readthedocs.io/",
    "football_role": "Football-only soccerdata adapter from football enrichment source inventory.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable",
      "live_scraping_in_pass_b",
      "production_dependency_without_site_terms_review"
    ],
    "notes": "Accounted for explicitly; does not block multisport Pass B.",
    "required_env_keys": [],
    "source_family": "soccerdata_library_adapter",
    "source_key": "soccerdata-sofascore",
    "target_sport_applicability": "Football-only library adapter; no direct target sport applicability.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://soccerdata.readthedocs.io/",
    "football_role": "Football-only soccerdata adapter from football enrichment source inventory.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable",
      "live_scraping_in_pass_b",
      "production_dependency_without_site_terms_review"
    ],
    "notes": "Accounted for explicitly; does not block multisport Pass B.",
    "required_env_keys": [],
    "source_family": "soccerdata_library_adapter",
    "source_key": "soccerdata-sofifa",
    "target_sport_applicability": "Football-only library adapter; no direct target sport applicability.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://soccerdata.readthedocs.io/",
    "football_role": "Football-only soccerdata adapter from football enrichment source inventory.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable",
      "live_scraping_in_pass_b",
      "production_dependency_without_site_terms_review"
    ],
    "notes": "Accounted for explicitly; does not block multisport Pass B.",
    "required_env_keys": [],
    "source_family": "soccerdata_library_adapter",
    "source_key": "soccerdata-understat",
    "target_sport_applicability": "Football-only library adapter; no direct target sport applicability.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof"
    ],
    "docs_url": "https://soccerdata.readthedocs.io/",
    "football_role": "Football-only soccerdata adapter from football enrichment source inventory.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "direct_multisport_provider_classification",
      "blocking_multisport_pass_when_unavailable",
      "live_scraping_in_pass_b",
      "production_dependency_without_site_terms_review"
    ],
    "notes": "Accounted for explicitly; does not block multisport Pass B.",
    "required_env_keys": [],
    "source_family": "soccerdata_library_adapter",
    "source_key": "soccerdata-whoscored",
    "target_sport_applicability": "Football-only library adapter; no direct target sport applicability.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "football_only_reference"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof",
      "terms_review_proof"
    ],
    "docs_url": "https://www.fotmob.com/",
    "football_role": "Football rich unofficial probe for context discovery.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "uncontrolled_scraping",
      "production_dependency_without_terms_review",
      "claiming_source_bound_shadow_ready"
    ],
    "notes": "Must remain excluded from Pass B source-bound shadow construction.",
    "required_env_keys": [],
    "source_family": "rich_unofficial_probe_only",
    "source_key": "fotmob-probe",
    "target_sport_applicability": "Probe-only pattern; not direct multisport source.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "deferred_probe_only"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof",
      "terms_review_proof"
    ],
    "docs_url": "https://www.sofascore.com/",
    "football_role": "Football rich unofficial Sofascore probe.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "uncontrolled_scraping",
      "production_dependency_without_terms_review",
      "claiming_source_bound_shadow_ready"
    ],
    "notes": "Can inform future research only after legal/terms review; not Pass B direct provider.",
    "required_env_keys": [],
    "source_family": "rich_unofficial_probe_only",
    "source_key": "sofascore-rich-probe",
    "target_sport_applicability": "Probe-only pattern; no production dependency.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "deferred_probe_only"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof",
      "terms_review_proof"
    ],
    "docs_url": "https://github.com/oseymour/ScraperFC",
    "football_role": "Bridge/probe around Sofascore-like rich context.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "uncontrolled_scraping",
      "production_dependency_without_terms_review",
      "claiming_source_bound_shadow_ready"
    ],
    "notes": "Represent in inventory but forbid production-selectable routes.",
    "required_env_keys": [],
    "source_family": "rich_unofficial_probe_only",
    "source_key": "scraperfc-sofascore-bridge",
    "target_sport_applicability": "Probe-only; not source-bound shadow provider.",
    "target_sports": [],
    "terms_or_access_review_required": true,
    "transfer_decision": "deferred_probe_only"
  },
  {
    "allowed_proof_levels": [
      "real_live_http_proof",
      "real_replay_corpus_proof",
      "docs_capability_only",
      "blocked_access_proof",
      "terms_review_proof"
    ],
    "docs_url": "https://developers.pandascore.co/",
    "football_role": "Pass A esports provider candidate for CS2/Dota2/Valorant.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "using_odds_markets_for_decisions",
      "calling_paid_only_endpoint_without_plan_proof"
    ],
    "notes": "Pass B may capture schedule/results/static data only; betting odds excluded from decisions.",
    "required_env_keys": [
      "PANDASCORE_API_KEY"
    ],
    "source_family": "esports_multisport_addition",
    "source_key": "pandascore",
    "target_sport_applicability": "Direct for CS2, Dota2 and Valorant only after API plan/terms and endpoint proof are verified.",
    "target_sports": [
      "cs2",
      "dota2",
      "valorant"
    ],
    "terms_or_access_review_required": true,
    "transfer_decision": "transfer_direct"
  },
  {
    "allowed_proof_levels": [
      "docs_capability_only",
      "blocked_access_proof",
      "terms_review_proof"
    ],
    "docs_url": "https://liquipedia.net/api-terms-of-use",
    "football_role": "Esports reference candidate.",
    "forbidden_uses": [
      "production_selectable_without_manual_authorization",
      "betting_decisions_or_edges",
      "fallback_provider_ids_or_scores",
      "raw_headers_tokens_cookies_or_api_keys_in_reports",
      "production_db_writes",
      "betting_data_writes",
      "uncontrolled_scraping",
      "production_dependency_without_terms_review",
      "claiming_source_bound_shadow_ready",
      "exceeding_liquipedia_rate_limits"
    ],
    "notes": "MediaWiki/LiquipediaDB access requires terms/rate review and possibly dashboard approval.",
    "required_env_keys": [],
    "source_family": "esports_multisport_addition",
    "source_key": "liquipedia-reference",
    "target_sport_applicability": "Reference/deferred only for CS2, Dota2 and Valorant; no uncontrolled scraping.",
    "target_sports": [
      "cs2",
      "dota2",
      "valorant"
    ],
    "terms_or_access_review_required": true,
    "transfer_decision": "deferred_probe_only"
  }
]
"""

@dataclass(frozen=True)
class SourceInventoryEntry:
    source_key: str
    source_family: str
    football_role: str
    target_sport_applicability: str
    transfer_decision: str
    target_sports: tuple[str, ...]
    required_env_keys: tuple[str, ...]
    allowed_proof_levels: tuple[str, ...]
    forbidden_uses: tuple[str, ...]
    notes: str
    docs_url: str
    terms_or_access_review_required: bool

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "SourceInventoryEntry":
        return cls(
            source_key=payload["source_key"],
            source_family=payload["source_family"],
            football_role=payload["football_role"],
            target_sport_applicability=payload["target_sport_applicability"],
            transfer_decision=payload["transfer_decision"],
            target_sports=tuple(payload["target_sports"]),
            required_env_keys=tuple(payload["required_env_keys"]),
            allowed_proof_levels=tuple(payload["allowed_proof_levels"]),
            forbidden_uses=tuple(payload["forbidden_uses"]),
            notes=payload["notes"],
            docs_url=payload["docs_url"],
            terms_or_access_review_required=bool(payload["terms_or_access_review_required"]),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_family": self.source_family,
            "football_role": self.football_role,
            "target_sport_applicability": self.target_sport_applicability,
            "transfer_decision": self.transfer_decision,
            "target_sports": list(self.target_sports),
            "required_env_keys": list(self.required_env_keys),
            "allowed_proof_levels": list(self.allowed_proof_levels),
            "forbidden_uses": list(self.forbidden_uses),
            "notes": self.notes,
            "docs_url": self.docs_url,
            "terms_or_access_review_required": self.terms_or_access_review_required,
        }


def build_source_inventory() -> tuple[SourceInventoryEntry, ...]:
    return tuple(SourceInventoryEntry.from_json(item) for item in json.loads(_SOURCE_JSON))


def inventory_by_key() -> dict[str, SourceInventoryEntry]:
    return {entry.source_key: entry for entry in build_source_inventory()}


def source_inventory_report_payload() -> dict[str, Any]:
    inventory = sorted(build_source_inventory(), key=lambda item: item.source_key)
    return {
        "inventory_version": "ms-b-source-inventory-v1",
        "target_sports": list(TARGET_SPORTS),
        "football_era_source_count": len(FOOTBALL_ERA_SOURCE_KEYS),
        "source_count": len(inventory),
        "sources": [entry.to_json() for entry in inventory],
    }


def write_source_inventory_report(path: str = "reports/multisport_foundation/pass_b/source_inventory_carry_forward.json") -> str:
    import os
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(source_inventory_report_payload(), indent=2, sort_keys=True) + "\n")
    return path
