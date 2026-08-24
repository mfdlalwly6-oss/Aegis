-- 002_investigator_workflow — historical migration.
-- No-op on a fresh PostgreSQL baseline because 001 already carries these
-- columns. Kept for migration-history parity with the SQLite evolution.
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS notes_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS resolution TEXT;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS resolution TEXT;
