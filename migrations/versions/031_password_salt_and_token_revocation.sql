-- 031_password_salt_and_token_revocation.sql
-- ═══════════════════════════════════════════════════════════════════════════
-- Security hardening — two additive, backward-compatible columns on `users`:
--
-- 1) password_salt TEXT (nullable)
--    Per-user random salt for PBKDF2-SHA256. NULL = legacy hash that used the
--    old fixed SECRET_KEY-derived salt. Legacy hashes keep verifying; on the
--    next successful login / password set the account is transparently
--    rehashed with a fresh random salt (opportunistic migration — NO lockout).
--
-- 2) tokens_valid_after TEXT (nullable, ISO-8601 UTC)
--    Server-side JWT revocation without a session table: a merchant/owner JWT
--    is accepted only when its `iat` >= tokens_valid_after. Set on:
--      - account disable      → immediate revocation of all live tokens
--      - password set/reset   → all sessions issued before the change die
--    NULL = no floor (legacy behavior). Combined with the per-request
--    status='active' check in require_merchant this makes disable/revoke
--    instant and password-rotation invalidating, with zero schema for a
--    session store and no per-token denylist to sweep.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_salt TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS tokens_valid_after TEXT;

-- Index to keep the per-request revocation lookup cheap (user_id is the PK,
-- so no extra index is required for require_merchant's point lookup; this
-- partial index only accelerates admin sweeps of recently-rotated accounts).
CREATE INDEX IF NOT EXISTS idx_users_tokens_valid_after
  ON users (tokens_valid_after)
  WHERE tokens_valid_after IS NOT NULL;
