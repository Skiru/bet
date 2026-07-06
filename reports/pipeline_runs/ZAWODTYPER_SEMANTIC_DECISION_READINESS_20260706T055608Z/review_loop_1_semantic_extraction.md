# Loop 1 Review — Semantic Extraction Review

This review analyzes the top 20 picks extracted from ZawodTyper during the live execution on 2026-07-06.

## 1. Event Extraction Accuracy
*   **Observations**: All 19 unique event names were extracted correctly. Separators like `vs`, `v`, and dashes `[-–—]` were successfully parsed.
*   **Preservation**: Clean team/player designations were preserved with Polish characters intact (e.g. `Meksyk`, `Portugalia`, `Piłka Ręczna`). No crucial team suffixes like `II` or junior/reserves tags were truncated.
*   **Result**: `PASS_SEMANTIC_EVENT_EXTRACTION` (100% precision, zero data-loss of unique fixtures).

## 2. Market and Direction Parsing
*   **Observations**: Complex combo markets and bet-builders are cleanly preserved as raw strings. The market family classifier correctly assigns `unknown` to bet-builders to prevent line-parsing corruption, while simpler over/under and winner markets are correctly mapped (e.g. `btts`, `goals`, `handicap`, `winner`).
*   **Direction Mapping**: Correctly resolved `OVER`, `UNDER`, `WIN`, and `DC` directions.
*   **Result**: `PASS_SEMANTIC_MARKET_PARSING` (Accurate classification of standard lines, zero line hallucinations on multi-leg builders).

## 3. Reasoning and Metadata Context
*   **Observations**: The track records (e.g. `75% (4 bets)`) and names of individual tipsters are perfectly preserved and prefixed to the reasoning text. Length limits (800 characters) are respected, and no promo text or sidebar links were included.
*   **Odds Decimal**: Parsed correctly and treated as reference-only.
*   **Result**: `PASS_SEMANTIC_METADATA_CONTEXT` (Comprehensive capture of qualititative rationale).
