# Persistence Contract

- A4 introduces a generic scanner/evidence/fact/completeness store contract.
- Safe implementations in this phase are `InMemoryProductionEnrichmentStore` for tests and `FileBackedProductionEnrichmentStore` for temp/report persistence.
- Evidence metadata is persisted separately from scanner input and facts.
- Raw payloads are not embedded inside persisted evidence records; temp/report stores keep payload sidecars for offline reuse only.
- Production DB activation remains deferred because existing canonical fixture tables cannot safely express scanner-event-first persistence.
