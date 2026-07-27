"""Step business models and contract registrations."""
from __future__ import annotations

from src.bet.pipeline.contracts.base import CompletionEnvelopeType, ArtifactRole
from src.bet.pipeline.contracts.registry import ContractDescriptor, GLOBAL_CONTRACT_REGISTRY

from src.bet.pipeline.contracts.steps.s0_to_s2 import (
    S0HistoricalPnlV1,
    S1FixturesShortlistV1,
    S1eCanonicalEventUniverseV1,
    S2TipsterConsensusV1,
    S23EnrichmentGapsV1,
    S25ProviderObservationsV1,
    S27ReconciledFactsV1,
    S29DataReadinessV1,
)
from src.bet.pipeline.contracts.steps.s3_to_s10 import (
    S3CalibratedProbabilitiesV1,
    S4ExpectedValueEstimatesV1,
    S5ContextMotivationRiskV1,
    S6PortfolioRepeatGuardV1,
    S7ApprovedPicksV1,
    S7bSuperbetManualMappingV1,
    S8SuperbetManualQuotePackV1,
    S9ExecutedBetsJournalV1,
    S10SettlementHandoffV1,
)


def register_all_contracts() -> None:
    descriptors = [
        ContractDescriptor(
            contract_id="S0_HISTORICAL_PNL",
            schema_version=1,
            model_type=S0HistoricalPnlV1,
            envelope_type=CompletionEnvelopeType.SCRIPT_EVIDENCE,
            producer_step="S0",
            consumer_steps=("S1",),
        ),
        ContractDescriptor(
            contract_id="S1_FIXTURES_SHORTLIST",
            schema_version=1,
            model_type=S1FixturesShortlistV1,
            envelope_type=CompletionEnvelopeType.SCRIPT_EVIDENCE,
            producer_step="S1",
            consumer_steps=("S1e",),
        ),
        ContractDescriptor(
            contract_id="S1E_CANONICAL_EVENT_UNIVERSE",
            schema_version=1,
            model_type=S1eCanonicalEventUniverseV1,
            envelope_type=CompletionEnvelopeType.SCRIPT_EVIDENCE,
            producer_step="S1e",
            consumer_steps=("S2",),
        ),
        ContractDescriptor(
            contract_id="S2_TIPSTER_CONSENSUS",
            schema_version=1,
            model_type=S2TipsterConsensusV1,
            envelope_type=CompletionEnvelopeType.SCRIPT_EVIDENCE,
            producer_step="S2",
            consumer_steps=("S2.3",),
        ),
        ContractDescriptor(
            contract_id="S2_3_ENRICHMENT_GAPS",
            schema_version=1,
            model_type=S23EnrichmentGapsV1,
            envelope_type=CompletionEnvelopeType.AGENT_ARTIFACT,
            producer_step="S2.3",
            consumer_steps=("S2.5",),
        ),
        ContractDescriptor(
            contract_id="S2_5_PROVIDER_OBSERVATIONS",
            schema_version=1,
            model_type=S25ProviderObservationsV1,
            envelope_type=CompletionEnvelopeType.AGENT_ARTIFACT,
            producer_step="S2.5",
            consumer_steps=("S2.7",),
        ),
        ContractDescriptor(
            contract_id="S2_7_RECONCILED_FACTS",
            schema_version=1,
            model_type=S27ReconciledFactsV1,
            envelope_type=CompletionEnvelopeType.AGENT_ARTIFACT,
            producer_step="S2.7",
            consumer_steps=("S2.9",),
        ),
        ContractDescriptor(
            contract_id="S2_9_DATA_READINESS",
            schema_version=1,
            model_type=S29DataReadinessV1,
            envelope_type=CompletionEnvelopeType.AGENT_ARTIFACT,
            producer_step="S2.9",
            consumer_steps=("S3", "S5"),
        ),
        ContractDescriptor(
            contract_id="S3_CALIBRATED_PROBABILITIES",
            schema_version=1,
            model_type=S3CalibratedProbabilitiesV1,
            envelope_type=CompletionEnvelopeType.SCRIPT_EVIDENCE,
            producer_step="S3",
            consumer_steps=("S4",),
        ),
        ContractDescriptor(
            contract_id="S4_EXPECTED_VALUE_ESTIMATES",
            schema_version=1,
            model_type=S4ExpectedValueEstimatesV1,
            envelope_type=CompletionEnvelopeType.SCRIPT_EVIDENCE,
            producer_step="S4",
            consumer_steps=("S5",),
        ),
        ContractDescriptor(
            contract_id="S5_CONTEXT_MOTIVATION_RISK",
            schema_version=1,
            model_type=S5ContextMotivationRiskV1,
            envelope_type=CompletionEnvelopeType.AGENT_ARTIFACT,
            producer_step="S5",
            consumer_steps=("S6",),
        ),
        ContractDescriptor(
            contract_id="S6_PORTFOLIO_REPEAT_GUARD",
            schema_version=1,
            model_type=S6PortfolioRepeatGuardV1,
            envelope_type=CompletionEnvelopeType.SCRIPT_EVIDENCE,
            producer_step="S6",
            consumer_steps=("S7",),
        ),
        ContractDescriptor(
            contract_id="S7_APPROVED_PICKS",
            schema_version=1,
            model_type=S7ApprovedPicksV1,
            envelope_type=CompletionEnvelopeType.SCRIPT_EVIDENCE,
            producer_step="S7",
            consumer_steps=("S7b", "S8"),
        ),
        ContractDescriptor(
            contract_id="S7B_SUPERBET_MANUAL_MAPPING",
            schema_version=2,
            model_type=S7bSuperbetManualMappingV1,
            envelope_type=CompletionEnvelopeType.SCRIPT_EVIDENCE,
            producer_step="S7b",
            consumer_steps=("S8",),
        ),
        ContractDescriptor(
            contract_id="S8_SUPERBET_MANUAL_QUOTE_PACK",
            schema_version=2,
            model_type=S8SuperbetManualQuotePackV1,
            envelope_type=CompletionEnvelopeType.SCRIPT_EVIDENCE,
            producer_step="S8",
            consumer_steps=("S9",),
        ),
        ContractDescriptor(
            contract_id="S9_EXECUTED_BETS_JOURNAL",
            schema_version=1,
            model_type=S9ExecutedBetsJournalV1,
            envelope_type=CompletionEnvelopeType.HUMAN_GATE,
            producer_step="S9",
            consumer_steps=("S10",),
        ),
        ContractDescriptor(
            contract_id="S10_SETTLEMENT_HANDOFF",
            schema_version=1,
            model_type=S10SettlementHandoffV1,
            envelope_type=CompletionEnvelopeType.STATE_MARKER,
            producer_step="S10",
            consumer_steps=(),
        ),
    ]

    for desc in descriptors:
        try:
            GLOBAL_CONTRACT_REGISTRY.register(desc)
        except ValueError:
            pass  # Already registered


register_all_contracts()
