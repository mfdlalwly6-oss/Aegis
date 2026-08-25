-- 010_rls_app_role_create — aegis_app needs CREATE on schema public because the
-- app's migrate() issues CREATE TABLE IF NOT EXISTS schema_migrations at boot.
-- Row-level data stays protected by RLS policies; CREATE here only allows the
-- migration bookkeeping table pattern.
GRANT CREATE ON SCHEMA public TO aegis_app;
