# Scanner Bridge Contract

- Scanner events are persisted as input records before enrichment.
- Provider evidence metadata and payload reuse are persisted separately from scanner input.
- Facts persist with `scanner_event_id`, `provider_event_id`, `evidence_identity`, and `schema_fingerprint`.
- Empty stores fail closed unless separately seeded.
- Force refresh bypasses cached completeness and requires fresh evidence; without a live fetcher in A4 it remains fail-closed.
- No prediction, valuation, staking, coupon, gate, or betting decision logic is imported or written.
