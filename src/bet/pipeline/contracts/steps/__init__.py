"""Step contracts registration for pipeline steps S0 through S10."""
from __future__ import annotations

from pydantic import Field
from bet.pipeline.contracts.base import StrictBaseModel, CompletionEnvelopeType, ArtifactRole
from bet.pipeline.contracts.registry import ContractDescriptor, GLOBAL_CONTRACT_REGISTRY
from bet.pipeline.contracts.steps.s3_to_s10 import (
    S7ApprovedPicksV1,
    S7bSuperbetManualMappingV1,
    S8SuperbetManualQuotePackV1,
)


class DummyStepModel(StrictBaseModel):
    pass


def _register_step_contracts() -> None:
    contracts = [
        ("S0_HISTORICAL_PNL", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S0", ("S1",)),
        ("S1_FIXTURES_SHORTLIST", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S1", ("S1e",)),
        ("S1E_CANONICAL_EVENT_UNIVERSE", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S1e", ("S2",)),
        ("S2_TIPSTER_CONSENSUS", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S2", ("S2.3",)),
        ("S2_3_ENRICHMENT_GAPS", 1, CompletionEnvelopeType.AGENT_ARTIFACT, "S2.3", ("S2.5",)),
        ("S2_5_PROVIDER_OBSERVATIONS", 1, CompletionEnvelopeType.AGENT_ARTIFACT, "S2.5", ("S2.7",)),
        ("S2_7_RECONCILED_FACTS", 1, CompletionEnvelopeType.AGENT_ARTIFACT, "S2.7", ("S2.9",)),
        ("S2_9_DATA_READINESS", 1, CompletionEnvelopeType.AGENT_ARTIFACT, "S2.9", ("S3",)),
        ("S3_CALIBRATED_PROBABILITIES", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S3", ("S4",)),
        ("S4_EXPECTED_VALUE_ESTIMATES", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S4", ("S5",)),
        ("S5_CONTEXT_MOTIVATION_RISK", 1, CompletionEnvelopeType.AGENT_ARTIFACT, "S5", ("S6",)),
        ("S6_PORTFOLIO_REPEAT_GUARD", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S6", ("S7",)),
        ("S7_APPROVED_PICKS", 1, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S7", ("S7b",), S7ApprovedPicksV1),
        ("S7B_SUPERBET_MANUAL_MAPPING", 2, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S7b", ("S8",), S7bSuperbetManualMappingV1),
        ("S8_SUPERBET_MANUAL_QUOTE_PACK", 2, CompletionEnvelopeType.SCRIPT_EVIDENCE, "S8", ("S9",), S8SuperbetManualQuotePackV1),
        ("S9_HUMAN_OPERATOR_APPROVAL", 1, CompletionEnvelopeType.HUMAN_GATE, "S9", ("S10",)),
        ("S9_EXECUTED_BETS_JOURNAL", 1, CompletionEnvelopeType.HUMAN_GATE, "S9", ("S10",)),
        ("S10_POSTEVENT_ACCOUNTING", 1, CompletionEnvelopeType.STATE_MARKER, "S10", ()),
        ("S10_SETTLEMENT_HANDOFF", 1, CompletionEnvelopeType.STATE_MARKER, "S10", ()),
    ]

    for item in contracts:
        cid, ver, env, producer, consumers = item[:5]
        model = item[5] if len(item) > 5 else DummyStepModel
        desc = ContractDescriptor(
            contract_id=cid,
            schema_version=ver,
            model_type=model,
            envelope_type=env,
            producer_step=producer,
            consumer_steps=consumers,
            artifact_role=ArtifactRole.PRIMARY,
        )
        try:
            GLOBAL_CONTRACT_REGISTRY.register(desc)
        except ValueError:
            pass


_register_step_contracts()
