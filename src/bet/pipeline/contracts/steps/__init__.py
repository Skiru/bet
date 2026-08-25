<<<<<<< HEAD
"""Step business models and contract registrations."""
=======
"""Step contracts registration for pipeline steps S0 through S10."""
>>>>>>> fix/bet-v5-final-one-pass-closure-v4
from __future__ import annotations

from bet.pipeline.contracts.base import CompletionEnvelopeType, ArtifactRole
from bet.pipeline.contracts.registry import ContractDescriptor, GLOBAL_CONTRACT_REGISTRY

from bet.pipeline.contracts.steps.s0_to_s2 import (
    S0HistoricalPnlV1,
    S1FixturesShortlistV1,
    S1eCanonicalEventUniverseV1,
    S2TipsterConsensusV1,
    S23EnrichmentGapsV1,
    S25ProviderObservationsV1,
    S27ReconciledFactsV1,
    S29DataReadinessV1,
)
from bet.pipeline.contracts.steps.s3_to_s10 import (
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


<<<<<<< HEAD
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
=======
def _register_step_contracts() -> None:
    contracts = [
        ("S0_HISTORICAL_PNL", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S0", ("S1",), S0HistoricalPnlV1),
        ("S1_FIXTURES_SHORTLIST", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S1", ("S1e",), S1FixturesShortlistV1),
        ("S1E_CANONICAL_EVENT_UNIVERSE", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S1e", ("S2",), S1eCanonicalEventUniverseV1),
        ("S2_TIPSTER_CONSENSUS", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S2", ("S2.3",), S2TipsterConsensusV1),
        ("S2_3_ENRICHMENT_GAPS", 1, CompletionEnvelopeType.AGENT_ARTIFACT, "S2.3", ("S2.5",), S23EnrichmentGapsV1),
        ("S2_5_PROVIDER_OBSERVATIONS", 1, CompletionEnvelopeType.AGENT_ARTIFACT, "S2.5", ("S2.7",), S25ProviderObservationsV1),
        ("S2_7_RECONCILED_FACTS", 1, CompletionEnvelopeType.AGENT_ARTIFACT, "S2.7", ("S2.9",), S27ReconciledFactsV1),
        ("S2_9_DATA_READINESS", 1, CompletionEnvelopeType.AGENT_ARTIFACT, "S2.9", ("S3",), S29DataReadinessV1),
        ("S3_CALIBRATED_PROBABILITIES", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S3", ("S4",), S3CalibratedProbabilitiesV1),
        ("S4_EXPECTED_VALUE_ESTIMATES", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S4", ("S5",), S4ExpectedValueEstimatesV1),
        ("S5_CONTEXT_MOTIVATION_RISK", 1, CompletionEnvelopeType.AGENT_ARTIFACT, "S5", ("S6",), S5ContextMotivationRiskV1),
        ("S6_PORTFOLIO_REPEAT_GUARD", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S6", ("S7",), S6PortfolioRepeatGuardV1),
        ("S7_APPROVED_PICKS", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S7", ("S7b",), S7ApprovedPicksV1),
        ("S7B_SUPERBET_MANUAL_MAPPING", 2, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S7b", ("S8",), S7bSuperbetManualMappingV1),
        ("S8_SUPERBET_MANUAL_QUOTE_PACK", 2, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S8", ("S9",), S8SuperbetManualQuotePackV1),
        ("S9_HUMAN_OPERATOR_APPROVAL", 1, CompletionEnvelopeType.HUMAN_GATE, "S9", ("S10",), S9ExecutedBetsJournalV1),
        ("S9_EXECUTED_BETS_JOURNAL", 1, CompletionEnvelopeType.HUMAN_GATE, "S9", ("S10",), S9ExecutedBetsJournalV1),
        ("S10_POSTEVENT_ACCOUNTING", 1, CompletionEnvelopeType.STATE_MARKER, "S10", (), S10SettlementHandoffV1),
        ("S10_SETTLEMENT_HANDOFF", 1, CompletionEnvelopeType.STATE_MARKER, "S10", (), S10SettlementHandoffV1),
    ]

    event_steps = {"S2", "S2.3", "S2.5", "S2.7", "S2.9", "S3", "S4", "S5"}
    for item in contracts:
        cid, ver, env, producer, consumers, model = item
        desc = ContractDescriptor(
            contract_id=cid,
            schema_version=ver,
            model_type=model,
            envelope_type=env,
            producer_step=producer,
            consumer_steps=consumers,
            artifact_role=ArtifactRole.PRIMARY,
            output_scope=(
                "event"
                if producer in event_steps
                else "human"
                if producer == "S9"
                else "run"
            ),
        )
        GLOBAL_CONTRACT_REGISTRY._descriptors[(cid, ver)] = desc


_register_step_contracts()
>>>>>>> fix/bet-v5-final-one-pass-closure-v4
