# Phase 1 Code and Artifact Review — ZawodTyper Semantic Extraction

This report presents a thorough analysis of the existing codebase and artifacts related to the safe, direct public-only public XHR scraping of ZawodTyper.

## 1. Extracted Fields from ZawodTyper
The scraper extracts the following key fields from the public XHR endpoint (`POST /wp-content/NP_ajax.php`):
*   `comment_id`: Unique ID of the tipster comment/pick.
*   `comment_type`: Filters for type `bet` only (regular chat comments are safely discarded).
*   `match_name`: Raw fixture name (e.g., "Team A - Team B" or "Player A vs Player B").
*   `content`: The qualitative analysis/reasoning written by the tipster.
*   `discipline`: Sports category name in Polish (e.g., "Piłka Nożna", "Tenis"), translated via `DISCIPLINE_MAP`.
*   `type`: Raw Polish bet type (e.g., "Obie strzelą (BTTS)" or "Powyżej 2.5 bramki").
*   `rate`: Raw decimal odds (e.g., "1.95").
*   `author_name`: The tipster's nickname.
*   `author_stats`: Dictionary containing performance metadata (`bet_count`, `ratio`).

## 2. Storage Locations for Core Properties
When converted to a `TipsterPick` object and written to JSON/SQLite:
*   **Event**: Stored in `event` (as `Home vs Away` after cleaning), `home_team`, and `away_team`.
*   **Sport**: Stored in `sport` (mapped to normalized English categories, defaulting to `football`).
*   **Market**: Stored in `market` (raw Polish/English text representation) and classified under `market_family` (e.g., `winner`, `goals`, `handicap`, `btts`, `correct_score`, `unknown`). The direction is parsed into `direction` (e.g., `OVER`, `UNDER`, `WIN`, `HOME`, `AWAY`, `DC`, `DNB`, `OTHER`).
*   **Odds**: Stored in `odds_decimal` (JSON) and `odds_decimal` (SQLite column).
*   **Reasoning**: Stored in `reasoning` (capped at 800 characters) containing tipster name, accuracy, and text content.
*   **Author/Tipster**: Stored in `tipster_name`.
*   **Accuracy/Source Quality**: Accuracy percentage (derived from `ratio`) is mapped to `accuracy_pct` (reference-only) and converted to a warning `accuracy_pct_reference_only`. The calculated score is saved as `extraction_quality` and metadata is stored in `valuable_signals.source_quality`.

## 3. Safe Event Name Normalization
Yes. `clean_team_name` strips tags, removes trailing market/UI artifacts (e.g., specific betting indicators like `(1)`, `(2)`, `[1X]`), and filters out terms in `TEAM_NOISE`. In `parse_zawodtyper_xhr_bets`, events are safely split using Polish dash variants `[-–—]` and `vs` with strict length checks (both sides must be `>= 2` characters) to prevent corrupted or truncated name parsing.

## 4. Combo/Bet-Builder Markets Representation
Multi-leg combo bets (e.g., "Hiszpania +0.5 gola + Portugalia -2.5 gola + Awans Hiszpania") are preserved as a single raw string under the `market` field. They are classified as `market_family = "unknown"`, preventing the pipeline from fabricating combined odds or incorrectly guessing their market lines. The raw odds fetched from the source are saved in `odds_decimal` as a **reference-only** parameter.

## 5. Rationale/Reasoning Text Preservation
Yes. The complete content block is extracted, stripped of HTML tags via `strip_html_text`, and prepended with the tipster's track record (e.g., `Tipster Jakub: 75% (4 bets)`). It is preserved up to 800 characters, maintaining full semantic context for downstream manual/operator review.

## 6. Author/Tipster Track Record Preservation
Yes. The tipster's nickname is stored in `tipster_name`. The track record (`bet_count` and `ratio`) is used to compute `accuracy_pct`.

## 7. Odds Decimal is Reference-Only
Yes. The `convert_legacy_pick_to_v2` logic explicitly appends `odds_reference_only` to the warnings list whenever `odds_decimal` is set. Furthermore, `odds_decimal` is labeled as `confidence_label = "source_claim"`, clearly signaling to downstream agents that these are historical/source-reported odds.

## 8. Safe Context Usage (No Auto Final Bet)
Yes. The pipeline contract restricts tipster picks to:
*   `s2_tipster_evidence`
*   `s3_context_cross_check`
*   `legacy_bridge_reference_only`

The adapter enforces `decision_boundary = "evidence_only_not_a_bet"`. This guarantees that under no circumstances can a tipster pick trigger automated coupon builders, EV calculations, or staking decisions. It remains context-only evidence.

## 9. Data-Loss and Hallucination Risks
*   **Data-Loss**: Low. Only non-bet comments and duplicates are pruned during deduplication (as certified in `coverage_reconciliation.json`). The pagination logic covers 505 items (XHR page 2), capturing the full daily corpus.
*   **Hallucination**: Very low. The system does not attempt to parse line numbers for complex bet-builders or "unknown" markets. If a market type is unclear, it safely defaults to `market_family = "unknown"` and `direction = "OTHER"` (or `WIN`/`OVER`/`UNDER` based on explicit keywords).
