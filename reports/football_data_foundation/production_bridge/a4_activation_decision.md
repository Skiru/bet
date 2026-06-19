# A4 Activation Decision

- Matrix activation: `MATRIX_ACTIVATION_DEFERRED`
- Routing activation: `ROUTING_ACTIVATION_DEFERRED`
- Production DB adapter: `DB_ACTIVATION_DEFERRED`

The persistence bridge is accepted as a production-safe scanner-to-enrichment adapter surface, but not yet as a production matrix/routing or canonical DB activation. Existing routing and DB conventions do not yet prove enrichment-only isolation or scanner-event-safe canonical persistence.
