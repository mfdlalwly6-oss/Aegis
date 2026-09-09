-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 028 — Migrate legacy policy_json thresholds into threshold_profiles
--
-- Some institutions already store decision thresholds inside tenants.policy_json
-- (the legacy path). This migrates those into the new threshold_profiles table
-- as ACTIVE tenant overrides so threshold_profiles becomes the single source of
-- truth (no conflicting sources). Values are clamped to the safe bounds and the
-- ordering (challenge<=review<=block) is enforced before insert. Idempotent.
-- ═══════════════════════════════════════════════════════════════════════════

INSERT INTO threshold_profiles
  (profile_id, scope, tenant_id, challenge, review, block, fx_missing_action, active, created_by, created_at, updated_at, note)
SELECT
  'thp_mig_' || substr(md5(t.tenant_id), 1, 20),
  'tenant',
  t.tenant_id,
  -- clamp challenge into [0.20, 0.50]
  GREATEST(0.20, LEAST(0.50, COALESCE((t.policy_json::jsonb #>> '{thresholds,challenge}')::numeric, 0.35))),
  -- clamp review into [0.40, 0.75] AND keep it >= challenge (ordering)
  GREATEST(
    GREATEST(0.40, LEAST(0.75, COALESCE((t.policy_json::jsonb #>> '{thresholds,review}')::numeric, 0.60))),
    GREATEST(0.20, LEAST(0.50, COALESCE((t.policy_json::jsonb #>> '{thresholds,challenge}')::numeric, 0.35)))
  ),
  -- clamp block into [0.60, 0.95] AND keep it >= review (ordering)
  GREATEST(
    GREATEST(0.60, LEAST(0.95, COALESCE((t.policy_json::jsonb #>> '{thresholds,block}')::numeric, 0.80))),
    GREATEST(
      GREATEST(0.40, LEAST(0.75, COALESCE((t.policy_json::jsonb #>> '{thresholds,review}')::numeric, 0.60))),
      GREATEST(0.20, LEAST(0.50, COALESCE((t.policy_json::jsonb #>> '{thresholds,challenge}')::numeric, 0.35)))
    )
  ),
  -- fx_missing_action: only review/block allowed (never a silent allow)
  CASE
    WHEN (t.policy_json::jsonb ->> 'fx_missing_action') IN ('review','block')
      THEN (t.policy_json::jsonb ->> 'fx_missing_action')
    ELSE 'review'
  END,
  1,
  'migration-028',
  to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.FF6"Z"'),
  to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.FF6"Z"'),
  'migrated from policy_json (legacy)'
FROM tenants t
WHERE t.deleted_at IS NULL
  AND t.policy_json LIKE '%thresholds%'
  -- only rows that actually carry a numeric threshold
  AND (t.policy_json::jsonb #>> '{thresholds,challenge}') IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM threshold_profiles tp
    WHERE tp.scope = 'tenant' AND tp.tenant_id = t.tenant_id
  )
ORDER BY t.tenant_id
ON CONFLICT ON CONSTRAINT uq_threshold_profiles_scope DO NOTHING;

-- NOTE on ordering: the clamped values are already within the DB CHECK bounds.
-- The chk_th_order CHECK (challenge<=review<=block) may reject a pathological
-- legacy row whose stored values violate ordering; such rows are intentionally
-- skipped by the migration (they stay on the default) and should be fixed via
-- the new threshold UI. No data is lost — policy_json is left untouched.
