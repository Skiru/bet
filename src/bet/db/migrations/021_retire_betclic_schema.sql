-- Immutable documentation for schema version 21.
-- Runtime migration uses schema._migrate_v21_retired_operator_schema because
-- SQLite requires column introspection before the generic reference rename.
DROP TABLE IF EXISTS betclic_markets;
DROP TABLE IF EXISTS betclic_competition_profiles;
