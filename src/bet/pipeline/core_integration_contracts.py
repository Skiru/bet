"""Explicit contracts for the non-enrichment core integration surface."""
from __future__ import annotations

import os
from dataclasses import dataclass

from bet.pipeline.runtime_modes import LIVE_ACK_KEY, LIVE_ACK_VALUE, RuntimeMode, parse_runtime_mode


@dataclass(frozen=True)
class CoreIntegrationContract:
    stage: str
    source: str
    transport: str
    artifact_role: str
    timeout_seconds: int
    live_network: bool = True
    requires_live_ack: bool = True
    notes: str = ""

    @property
    def contract_id(self) -> str:
        return f"{self.stage}:{self.source}"


CORE_INTEGRATION_CONTRACTS: tuple[CoreIntegrationContract, ...] = (
    CoreIntegrationContract("S1", "SofaScore", "http_json", "fixture_identity", 20, notes="Discovery corroboration only."),
    CoreIntegrationContract("S1", "The Odds API", "http_json", "fixture_identity", 30, notes="Discovery corroboration only."),
    CoreIntegrationContract("S1", "API-Football", "http_json", "fixture_identity", 30, notes="Discovery corroboration only."),
    CoreIntegrationContract("S2", "ZawodTyper", "playwright_xhr", "tipster_consensus", 30, notes="XHR-first NP_ajax capture with DOM fallback."),
    CoreIntegrationContract("S2", "Typersi", "playwright_dom", "tipster_consensus", 30),
    CoreIntegrationContract("S2", "Sportsgambler", "http_html", "tipster_consensus", 30),
    CoreIntegrationContract("S2", "PicksWise", "playwright_dom", "tipster_consensus", 30),
    CoreIntegrationContract("S2", "BetIdeas", "playwright_dom", "tipster_consensus", 30),
    CoreIntegrationContract("S2", "Feedinco", "http_html", "tipster_consensus", 30),
    CoreIntegrationContract("S2", "BettingClosed", "http_html", "tipster_consensus", 30),
    CoreIntegrationContract("S4", "the-odds-api", "http_json", "odds_snapshot", 30),
    CoreIntegrationContract("S4", "odds-api-io", "http_json", "odds_snapshot", 30),
    CoreIntegrationContract("S4", "api-football-odds", "http_json", "odds_snapshot", 30),
    CoreIntegrationContract("S4", "evaluator", "local_compute", "odds_evaluation", 0, live_network=False, requires_live_ack=False),
    CoreIntegrationContract("S8", "coupon-builder", "local_compute", "coupon_artifact", 0, live_network=False, requires_live_ack=False),
)


_BY_STAGE: dict[str, tuple[CoreIntegrationContract, ...]] = {}
for _contract in CORE_INTEGRATION_CONTRACTS:
    _BY_STAGE.setdefault(_contract.stage, tuple())
_BY_STAGE = {
    stage: tuple(contract for contract in CORE_INTEGRATION_CONTRACTS if contract.stage == stage)
    for stage in {contract.stage for contract in CORE_INTEGRATION_CONTRACTS}
}


def contracts_for_stage(stage: str) -> tuple[CoreIntegrationContract, ...]:
    return _BY_STAGE.get(str(stage or "").strip(), ())


def contract_sources_for_stage(stage: str) -> tuple[str, ...]:
    return tuple(contract.source for contract in contracts_for_stage(stage))


def get_contract(stage: str, source: str) -> CoreIntegrationContract:
    source_key = str(source or "").strip().lower()
    for contract in contracts_for_stage(stage):
        if contract.source.lower() == source_key:
            return contract
    raise KeyError(f"Unknown core integration contract for {stage}/{source}")


def runtime_managed(environ: dict[str, str] | None = None) -> bool:
    env = environ or os.environ
    return bool(env.get("BET_PIPELINE_RUNTIME_MODE"))


def live_integrations_allowed(
    stage: str,
    *,
    environ: dict[str, str] | None = None,
    runtime_mode: RuntimeMode | str | None = None,
) -> tuple[bool, str]:
    env = environ or os.environ
    live_contracts = [contract for contract in contracts_for_stage(stage) if contract.live_network]
    if not live_contracts:
        return True, ""
    if runtime_mode is None:
        runtime_mode = env.get("BET_PIPELINE_RUNTIME_MODE", "")
    if not runtime_mode:
        return True, ""

    mode = parse_runtime_mode(runtime_mode)
    if mode not in {RuntimeMode.LIVE_SHADOW, RuntimeMode.PRODUCTION}:
        return False, "BLOCKED_LIVE_NETWORK_ACK_MISSING"
    if env.get(LIVE_ACK_KEY, "") != LIVE_ACK_VALUE:
        return False, "BLOCKED_LIVE_NETWORK_ACK_MISSING"
    return True, ""


def require_live_integrations(
    stage: str,
    *,
    environ: dict[str, str] | None = None,
    runtime_mode: RuntimeMode | str | None = None,
) -> None:
    allowed, reason = live_integrations_allowed(stage, environ=environ, runtime_mode=runtime_mode)
    if not allowed:
        raise RuntimeError(reason)
