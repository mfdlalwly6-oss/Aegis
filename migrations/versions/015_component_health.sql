-- Component health evidence on decisions: records which risk engines were
-- healthy/degraded/unavailable at decision time, the weight actually applied
-- after availability-aware renormalization, and the degraded-mode flag.
-- Additive only; no data loss. Existing rows keep defaults.
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS component_health_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS degraded_mode INTEGER NOT NULL DEFAULT 0;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS degraded_reason TEXT;
