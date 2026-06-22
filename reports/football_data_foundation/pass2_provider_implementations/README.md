# Football Enrichment Pass 2 Provider Implementations and Replay Parsers

## Summary of Pass 2
Pass 2 introduces robust shadow provider clients, HTTP JSON transport, and sanitized replay/open-data parsers, completing the source-coverage matrix for the Football Data Foundation.

### Key Tenets and Guardrails
* **No Production Activation:** This pass does not active any production routing/matrix. All data remain strictly shadow-only and `selectable_for_production=False` is enforced.
* **Credential-Gated Current Clients:** Live provider clients (SportDB, football-data.org, Highlightly) require specific API keys and raise `CredentialsMissingError` if they are missing. They run transport only via shadow methods.
* **Deterministic Mock Transport:** All unit and integration tests run strictly using `MockHttpJsonTransport` with zero network calls.
* **Sanitized Replays:** Replay fixtures represent sanitized/synthetic proofs, not live proof or production database mutations.
* **Historical/Open Data:** Local open-data (StatsBomb, OpenFootball, Kaggle) and soccerdata parses are historical deep context only, and are marked with `is_current_truth_allowed=False`.
* **Zero Blind Live Scraping:** No live scraping is allowed; soccerdata and scraper bridges are restricted to sanitized replay parsers.

## Roadmap to Pass 3
Pass 3 will implement:
* Multi-source `FactFusion` rules
* Shadow Artifact generation
* Final automated production certification gates
