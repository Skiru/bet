from __future__ import annotations

from bet.pipeline.core_integration_contracts import contract_sources_for_stage
from bet.pipeline.core_integration_inventory import INTEGRATIONS_REVIEWED, inventory_paths


EXPECTED_PATHS = {
    "scripts/build_shortlist.py",
    "scripts/check_48h_repeats.py",
    "scripts/coupon_builder.py",
    "scripts/deep_stats_report.py",
    "scripts/fetch_odds_multi.py",
    "scripts/gate_checker.py",
    "scripts/odds_evaluator.py",
    "scripts/pipeline_steps/_runner.py",
    "scripts/pipeline_steps/s0_settler.py",
    "scripts/pipeline_steps/s1_discover.py",
    "scripts/pipeline_steps/s2_tipsters.py",
    "scripts/pipeline_steps/s3_stats.py",
    "scripts/pipeline_steps/s4_valuator.py",
    "scripts/pipeline_steps/s5_gate.py",
    "scripts/pipeline_steps/s6_repeats.py",
    "scripts/pipeline_steps/s7_validate.py",
    "scripts/pipeline_steps/s8_build_coupons.py",
    "scripts/settle_on_finish.py",
    "scripts/tipster_aggregator.py",
    "scripts/tipster_xref.py",
    "src/bet/pipeline/runtime_modes.py",
    "src/bet/pipeline/runtime_paths.py",
    "src/bet/pipeline/state.py",
    "src/bet/pipeline/wrapper_runtime_certification.py",
    "src/bet/api_clients/tipster_playwright.py",
    "config/pipeline_manifest.json",
}


def test_inventory_covers_all_reviewed_paths():
    assert set(inventory_paths()) == EXPECTED_PATHS


def test_stage_contracts_are_explicit():
    assert contract_sources_for_stage("S1") == ("SofaScore", "The Odds API", "API-Football")
    assert contract_sources_for_stage("S2") == (
        "ZawodTyper",
        "Typersi",
        "Sportsgambler",
        "PicksWise",
        "BetIdeas",
        "Feedinco",
        "BettingClosed",
    )
    assert contract_sources_for_stage("S4") == (
        "the-odds-api",
        "odds-api-io",
        "api-football-odds",
        "evaluator",
    )
    assert contract_sources_for_stage("S7b") == ()


def test_integrations_reviewed_matches_contracts():
    assert INTEGRATIONS_REVIEWED["S1"] == contract_sources_for_stage("S1")
    assert INTEGRATIONS_REVIEWED["S2"] == contract_sources_for_stage("S2")
    assert INTEGRATIONS_REVIEWED["S4"] == contract_sources_for_stage("S4")
    assert "S7b" not in INTEGRATIONS_REVIEWED
