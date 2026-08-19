# AEGIS Engineering Audit — 2026-08-19 (baseline commit b2c6eda)

Read-only findings before the tenant-scoping rebuild:

1. `investigators` table has NO `tenant_id` → investigators are platform-level, violating the required institution-scoped model.
2. `tenants` has no `investigator_limit` → no backend-enforced cap on investigators per institution.
3. No Institution Owner (tenant_owner) account model: merchant login is API-key only; no email/password role separation.
4. Investigator API queries are tenant-blind: any logged-in investigator sees ALL alerts/cases/decisions (cross-tenant leak).
5. No reports system (daily/weekly/monthly) and no PDF generation.
6. No backend enforcement that a `suspended` tenant's webhook is refused beyond `by_api_key(status='active')` (partial, not tested).
7. Tenant management lacks: plan/limit update, suspend/activate lifecycle (only delete/soft-delete exists).
8. Merchant portal has no investigators management, no manual-review listing, no dashboard aggregation endpoint.
9. Tests cover investigator flows but only as platform-level accounts; no multi-tenant isolation tests exist.
10. Frontends read some fields that mismatch backend responses (previously fixed for several; recheck after rebuild).
