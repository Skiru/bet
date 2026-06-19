# DB Schema Discovery

- Production SQLite convention exists in code via `config/betting_config.json`, `src/bet/db/schema.py`, and `src/bet/db/migrations/`.
- Local `betting/data/betting.db` is absent, so this checkpoint is `DB_UNAVAILABLE` for live schema inspection and relies on code-level discovery.
- Existing persisted entities such as `fixture_sources`, `source_entity_reference`, `fixture_capability_observation`, `fixture_capability_projection`, and `sports_enrichment_run` assume canonical fixture/team IDs.
- A4 starts from `scanner_event_id` before canonical fixture mapping exists, so direct production DB activation is not safe in this phase.
- Safe outcome: explicit adapter interface plus temp/report stores; production DB activation stays deferred.
