-- Migration v17: add normalized payload persistence and append-only observation identity

ALTER TABLE fixture_capability_observation
    ADD COLUMN payload_json TEXT NOT NULL DEFAULT '';

DROP INDEX IF EXISTS idx_fixture_capability_observation_identity;

CREATE UNIQUE INDEX IF NOT EXISTS idx_fixture_capability_observation_identity
    ON fixture_capability_observation(
        canonical_fixture_id,
        team_id,
        capability,
        source,
        request_identity,
        COALESCE(evidence_bundle_id, ''),
        valid_at,
        COALESCE(payload_sha256, '')
    );
