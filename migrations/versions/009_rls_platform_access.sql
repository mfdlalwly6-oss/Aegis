-- 009_rls_platform_access — platform context (owner/system) sees all rows.
-- GUC app.tenant_id='platform' = trusted platform operator scope; the API owner
-- token gates who can obtain that context. Tenant contexts stay isolated.
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['tenants','users','transactions','decisions','alerts','cases','account_profiles','webhooks_seen','audit_log'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format('DROP POLICY IF EXISTS audit_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I
         USING (current_setting(''app.tenant_id'', true) = ''platform''
                OR tenant_id = current_setting(''app.tenant_id'', true))
         WITH CHECK (current_setting(''app.tenant_id'', true) = ''platform''
                OR tenant_id = current_setting(''app.tenant_id'', true))', t);
  END LOOP;
  -- rules: platform sees all; tenants see platform defaults (NULL) + own
  DROP POLICY IF EXISTS rules_isolation ON rules;
  CREATE POLICY tenant_isolation ON rules
    USING (current_setting('app.tenant_id', true) = 'platform'
           OR tenant_id IS NULL
           OR tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (current_setting('app.tenant_id', true) = 'platform'
           OR tenant_id IS NULL
           OR tenant_id = current_setting('app.tenant_id', true));
  -- investigators: platform sees all (incl. platform staff); tenants see own
  DROP POLICY IF EXISTS tenant_isolation ON investigators;
  CREATE POLICY tenant_isolation ON investigators
    USING (current_setting('app.tenant_id', true) = 'platform'
           OR tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (current_setting('app.tenant_id', true) = 'platform'
           OR tenant_id = current_setting('app.tenant_id', true));
END $$;
