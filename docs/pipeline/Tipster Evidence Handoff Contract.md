# Tipster Evidence Handoff Contract v1

## 1. Overview
The Tipster Evidence Handoff Contract defines how extracted tipster sentiment and reasoning is packaged at the end of Phase S2 and handed off to S3 (contextual cross-check), S4 (market sanity), and manual Superbet quote review. This contract strictly enforces an **evidence-only** boundary.

## 2. Structural Forbidden Actions
The handoff object and any of its child events MUST NOT contain or influence any of the following fields/actions:
- **EV (Expected Value)**
- **Stake / Sizing / Bankroll percentage**
- **Coupon / Ticket packaging**
- **Final bet decisions / Placements**
- **Superbet combined odds / Combined fixtures**

Odds presented in this handoff are **reference-only** historical attributes.

## 3. Downstream Agent Interpretation Policy
Any downstream agent consuming this handoff must adhere to the following directive:
> “Context/sanity/sentiment only; independently verify with stats and odds. Never use tipster claims as direct betting triggers.”

## 4. Handoff Schema Specification
```json
{
  "schema_version": "tipster_evidence_handoff_v1",
  "contract": "evidence_only_not_betting_decision",
  "source_stage": "S2 tipster evidence",
  "allowed_consumers": [
    "S3 contextual cross-check",
    "S4 market sanity",
    "manual Superbet quote review"
  ],
  "forbidden_actions": [
    "EV",
    "stake",
    "coupon",
    "final bet",
    "Superbet combined odds"
  ],
  "sources": [],
  "events": [
    {
      "normalized_event_key": "team_a|team_b",
      "event": "Team A vs Team B",
      "sport": "football",
      "markets": ["over 2.5 goals"],
      "tipster_sentiment": "OVER",
      "qualitative_reasoning_summaries": ["Narrative justification string"],
      "source_count": 1,
      "evidence_quality": "HIGH|MEDIUM|LOW",
      "needs_match_resolution": false,
      "needs_manual_review": false,
      "agent_use_decisions": ["USE_AS_CONTEXT"],
      "source_ids": ["zawodtyper"],
      "forbidden_actions": ["EV", "stake", "coupon", "final bet", "Superbet combined odds"]
    }
  ],
  "fail_closed": false
}
```

## 5. Match & Quality Flags
- **`needs_match_resolution`**: Set to `true` if team names could not be cleanly separated or mapped.
- **`needs_manual_review`**: Set to `true` if the reasoning text is missing, extremely short (< 30 characters), or low quality.
- **`fail_closed`**: Activated if all picks are rejected or no sources succeeded.
