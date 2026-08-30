-- Owner-only ALTER: session forensics column on investigators.
--
-- Separated from 018 because the app role (aegis_app) does NOT own the
-- investigators table and therefore cannot ALTER it; this statement must be
-- applied by the table owner (aegis). It is idempotent and safe to re-run.
-- The app's `investigators` listing query selects explicit columns, so this
-- column is read back via last_logout_at when present.
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS last_logout_at TEXT;
