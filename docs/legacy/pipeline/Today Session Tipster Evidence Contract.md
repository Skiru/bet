# Today Session Tipster Evidence Contract

## 1. Mandatory Pre-Step Execution
Every full daily session must run the certified shadow tipster evidence step before S3 (statistics analysis) and S4 (odds valuation):
```fish
scripts/pipeline_steps/s2_tipsters_shadow_evidence.py --include-certified-shadow
```

## 2. Session Agent Inputs
The session agent MUST read the following generated files:
- `certified_shadow.json`
- `certified_shadow_handoff.json`

## 3. Approved Uses (Context Only)
The session agent MUST include tipster evidence in its reasoning ONLY as:
- **Market Sanity**: Cross-checking proposed markets against wider community consensus.
- **Tipster Sentiment**: Capturing the aggregate directional bias of public tipsters.
- **Event/Context Cross-Check**: Matching fixture details and spotting discrepancies.
- **Manual Quote Review Context**: Providing extra background during final manual bookmaker quote verification.

## 4. Absolute Forbidden Uses (Boundaries)
The session agent MUST NOT use tipster evidence for:
- Expected Value (EV) calculations.
- Stake/sizing determinations.
- Coupon formulation.
- Final bet selection.
- Superbet combined odds generation.
- Automatic betting recommendation.

To prevent leaks, the following explicit forbidden terms must never be produced:
- `EV`
- `stake`
- `coupon`
- `final bet`
- `Superbet combined odds`

## 5. Typersi-Specific Rule
- Typersi is a static table tip/sentiment source.
- `REASONING_OK=0%` is expected.
- It can support market sentiment and consensus, but must never be used for qualitative or logical reasoning.

## 6. ZawodTyper-Specific Rule
- ZawodTyper can support qualitative community reasoning when reasoning is present in the extracted tips.
- It remains strictly evidence-only.

## 7. Operator-Risk-Specific Rule
- Operator-risk data is disabled by default.
- Enabling it requires `--allow-operator-risk-public-read` and local configuration via `tipster_operator_risk.local.json`.
- It is low-trust and manual-review-only.
- It cannot influence the final bet in any automated manner.

## 8. Full Session Readiness Parameters
A successful run requires:
- `total_picks > 0`
- `handoff_events > 0`
- `agent_readiness` 100% across all parsed picks
- Absolute absence of forbidden fields (e.g. `expected_value`, `stake_size`, `coupon_id`, `final_bet`, `superbet_combined_odds`)
- Runtime sources must exactly match `CERTIFIED_SHADOW_SOURCE_IDS` (equal to `zawodtyper` and `typersi`).
