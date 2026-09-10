-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 029 — Missing-FX action: four official options
--
-- Expands threshold_profiles.fx_missing_action from {review, block} to
-- {default, review, block, allow}:
--   default = follow the global system behavior (resolved at decision time,
--             currently REVIEW) — a real inheritance, not a copied value.
--   allow   = explicit policy-maker choice to tolerate missing FX and let the
--             normal threshold ladder decide (sanctions floor still applies).
--
-- The platform default row is switched to 'default' so it always tracks the
-- global behavior. Existing tenant overrides keep their explicit values.
-- Idempotent.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE threshold_profiles DROP CONSTRAINT IF EXISTS chk_th_fx;

ALTER TABLE threshold_profiles
  ADD CONSTRAINT chk_th_fx
  CHECK (fx_missing_action IN ('default','review','block','allow'));

-- Platform default profile now stores 'default' (follows global behavior).
UPDATE threshold_profiles
SET fx_missing_action = 'default',
    updated_at = to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.FF6"Z"')
WHERE scope = 'default' AND fx_missing_action NOT IN ('default');
