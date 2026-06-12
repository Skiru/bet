-- Migration v14: Add evidence linkage to team_form (REM-001B)
-- This migration adds source_event_ids and evidence_hash columns to team_form
-- to satisfy Gate 11 of the Sports Integration Live Review Contract.

-- Only run ALTER TABLE if the table exists (fresh DBs get columns from schema.sql)
-- SQLite doesn't support IF EXISTS for ALTER TABLE, so we use a workaround

-- Add source_event_ids column (JSON array of provider event IDs)
-- This will fail silently if column already exists (from schema.sql)
ALTER TABLE team_form ADD COLUMN source_event_ids TEXT NOT NULL DEFAULT '[]';

-- Add evidence_hash column (SHA-256 hash of evidence bundle)
ALTER TABLE team_form ADD COLUMN evidence_hash TEXT NOT NULL DEFAULT '';

-- Create index for evidence lookup by source event ID
-- SQLite doesn't support JSON array indexing directly, so we use LIKE for lookups
CREATE INDEX IF NOT EXISTS idx_team_form_source_events 
ON team_form(source_event_ids);

-- Create index for evidence hash lookup
CREATE INDEX IF NOT EXISTS idx_team_form_evidence_hash 
ON team_form(evidence_hash) 
WHERE evidence_hash != '';
