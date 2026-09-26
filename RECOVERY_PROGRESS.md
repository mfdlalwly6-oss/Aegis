# AEGIS Recovery Progress (2026-09-26)
- Branch: aegis-v3-main (local sandbox copy; real device zr0-ThinkPad-P52 UNREACHABLE via SSH ports 43607/52489)
- Completed: FX purge verified (fx_missing_action, DEFAULT_FX_ACTION, fxsel CSS), obsolete FX test removed
- Policy Studio: weights.py + thresholds.py routers registered; defaults Rules35/ML25/Graph15/AML15/Behavior10; thresholds 0.20/0.40/0.60
- Remaining: full pytest green run, real-device sync when SSH restored, GitHub push (no credentials in sandbox)
- Known: real device branch stage3-recovery has separate lineage; do NOT reset

## Update 2026-09-26 (batch 2)
- FIXED: policy_engine.py fx_missing_action purged (compile-verified)
- RESTORED: weights.py / thresholds.py routers from pre-FX reference (fx deps stripped)
- CLEANED: features.py fx residue
- PUSH: FAILED (no GitHub credentials in sandbox) — commits held locally
- REMAINING: full pytest green run, institution portal UI, real-device sync (SSH down)

## Update 2026-09-26 (batch 3 — final)
- POLICY_ENGINE: fx_missing_action fully purged, compile-verified
- THRESHOLDS router: restored from pre-FX reference, fx keys stripped, compile-verified
- WEIGHTS router: restored (139 lines), registered in api/v1/__init__.py
- FINAL FX SCAN (active code): fx_missing_action/renderFx/loadFx/fxsel = 0; fx_rates refs only in historical migrations (kept for migration-chain integrity)
- Commits: 63b8c3c, 8eb30e1, fe8e35d + this one — PUSH FAILED (no GitHub credentials in sandbox)
- SSH to real device (193.161.193.99:43607/52489): DOWN — real device untouched, local copy only

## Update 2026-09-26 (batch 4 — ZERO)
- orchestrator.py: dead fx_missing guard block removed (decision flows straight to _decide)
- policy_engine.py: fx docstring line removed
- pg_migrate.py: fx_rates removed from managed-tables list
- ACTIVE-CODE FX SCAN = 0 (only historical migrations retain fx table names — required for chain integrity)
- NOTE: thresholds.py router could not be restored cleanly from pre-FX ref (old file had pre-existing syntax quirks + fx coupling); weights.py restored OK. Policy thresholds live in policy_engine.py defaults (challenge 0.35/review 0.60/block 0.80 for wallet+payment).
- HEAD: see git log; PUSH: FAILED (no GitHub credentials in sandbox); SSH to real device: DOWN.

## Update 2026-09-26 (batch 5 — restore+port)
- VERIFIED via pre-FX evidence: DEFAULT_WEIGHTS = {rules:0.35, ml:0.25, graph:0.15, aml:0.15, behavior:0.10} in weight_repo.py (was present pre-FX) — weight_repo.py RESTORED fx-free.
- VERIFIED via pre-FX evidence: thresholds defaults 0.35/0.60/0.80 (wallet+payment), 0.40/0.65/0.85 (merchant), 0.45/0.70/0.88 (wholesale/real_estate), 0.30/0.55/0.78 (gov), clamps 0.20-0.50/0.40-0.75/0.60-0.95 — these ARE the pre-FX values (0.20/0.40/0.60 were clamp WINDOWS, not defaults).
- RESTORED: weight_repo.py (fx-free, compile-verified).
- threshold_repo.py: restore attempted, pre-FX file had fx coupling; repaired signature + stripped fx keys.
- PORTED: GET /institution/invitation (peek: valid|invalid|expired|revoked|used) + POST /institution/accept-invitation (consume, set password, activate, single-use token, tenant-active check, audit).
- Institution Portal as separate portal: NOT in pre-FX ref (portals = admin/merchant/investigator only) → classification E (never existed as separate portal; institution owner flow was via invitation email + accept page + login, all backend-driven).
- CONFIRMED: pre-FX admin UI had owner_email + owner_name fields (line 530-531) in create-institution form.
- SSH to real device: DOWN (unchanged). PUSH: pending credentials.

## Update 2026-09-26 (batch 6 — final wiring)
- threshold_repo.py: repaired pre-FX signature corruption (note: str|None=None duplication) + fx keys stripped — compile-gated restore.
- registry.py: WeightRepository/ThresholdRepository wired if absent (compile-gated, revert-on-fail).
- admin UI: owner_email/owner_name invitation fields ported into create-institution form (node --check gated).
- FX active-code scan: 0.
- PUSH: still blocked (no GitHub credentials); SSH to real device: DOWN. All work committed locally on aegis-v3-main.
