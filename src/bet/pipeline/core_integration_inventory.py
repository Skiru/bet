"""Inventory of the reviewed non-enrichment core pipeline integrations."""
from __future__ import annotations

from dataclasses import dataclass

from bet.pipeline.core_integration_contracts import contract_sources_for_stage


@dataclass(frozen=True)
class InventoryEntry:
    path: str
    stage: str
    role: str


CORE_INTEGRATION_INVENTORY: tuple[InventoryEntry, ...] = (
    InventoryEntry("scripts/build_shortlist.py", "S1", "shortlist_builder"),
    InventoryEntry("scripts/check_48h_repeats.py", "S6", "repeat_loss_guard"),
    InventoryEntry("scripts/coupon_builder.py", "S8", "coupon_constructor"),
    InventoryEntry("scripts/deep_stats_report.py", "S3", "stats_report"),
    InventoryEntry("scripts/fetch_odds_multi.py", "S4", "multi_source_odds_fetch"),
    InventoryEntry("scripts/gate_checker.py", "S7", "hard_gate"),
    InventoryEntry("scripts/odds_evaluator.py", "S4", "odds_evaluator"),
    InventoryEntry("scripts/pipeline_steps/_runner.py", "WRAPPER", "runtime_wrapper"),
    InventoryEntry("scripts/pipeline_steps/s0_settler.py", "S0", "settlement_wrapper"),
    InventoryEntry("scripts/pipeline_steps/s1_discover.py", "S1", "discovery_wrapper"),
    InventoryEntry("scripts/pipeline_steps/s2_tipsters.py", "S2", "tipster_wrapper"),
    InventoryEntry("scripts/pipeline_steps/s3_stats.py", "S3", "stats_wrapper"),
    InventoryEntry("scripts/pipeline_steps/s4_valuator.py", "S4", "valuator_wrapper"),
    InventoryEntry("scripts/pipeline_steps/s5_gate.py", "S7", "gate_wrapper"),
    InventoryEntry("scripts/pipeline_steps/s6_repeats.py", "S6", "repeat_wrapper"),
    InventoryEntry("scripts/pipeline_steps/s7_validate.py", "S7b", "betclic_wrapper"),
    InventoryEntry("scripts/pipeline_steps/s8_build_coupons.py", "S8", "coupon_wrapper"),
    InventoryEntry("scripts/settle_on_finish.py", "S0", "settlement_script"),
    InventoryEntry("scripts/tipster_aggregator.py", "S2", "tipster_aggregator"),
    InventoryEntry("scripts/tipster_xref.py", "S2", "tipster_cross_reference"),
    InventoryEntry("scripts/validate_betclic_markets.py", "S7b", "market_availability_validator"),
    InventoryEntry("src/bet/pipeline/runtime_modes.py", "RUNTIME", "runtime_mode_guard"),
    InventoryEntry("src/bet/pipeline/runtime_paths.py", "RUNTIME", "sandbox_paths"),
    InventoryEntry("src/bet/pipeline/state.py", "RUNTIME", "pipeline_state"),
    InventoryEntry("src/bet/pipeline/wrapper_runtime_certification.py", "RUNTIME", "wrapper_certification"),
    InventoryEntry("src/bet/api_clients/tipster_playwright.py", "S2", "playwright_tipster_client"),
    InventoryEntry("src/bet/scrapers/betclic.py", "S7b", "betclic_scraper"),
    InventoryEntry("config/pipeline_manifest.json", "MANIFEST", "pipeline_manifest"),
)


INTEGRATIONS_REVIEWED: dict[str, tuple[str, ...]] = {
    "S1": contract_sources_for_stage("S1"),
    "S2": contract_sources_for_stage("S2"),
    "S4": contract_sources_for_stage("S4"),
    "S7b": contract_sources_for_stage("S7b"),
    "S8": contract_sources_for_stage("S8"),
}


def inventory_paths() -> tuple[str, ...]:
    return tuple(entry.path for entry in CORE_INTEGRATION_INVENTORY)
