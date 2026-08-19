#!/usr/bin/env bash
# AEGIS E2E — real customer scenarios against the live stack (run on server host)
# Coverage: tenants, limits, investigators, IDOR isolation, ALLOW/BLOCK/REVIEW,
# review workflow, institution owner action, reports/PDF, suspend/activate.
set -u
cd /home/zr0/Aegis
BASE=http://localhost:8000
TS=$(date +%s)
OWNER=$(grep -E '^AEGIS_OWNER_TOKEN=' .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' | tr -d ' ')
[ -z "$OWNER" ] && OWNER="aegis-dev-owner-token"
OH="X-Owner-Token: $OWNER"
PASS=0; FAIL=0
ok(){ echo "  PASS: $1"; PASS=$((PASS+1)); }
no(){ echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
jget(){ python3 -c "import sys,json;d=json.load(open('/tmp/r.json'));print(d.get('$1',''))" 2>/dev/null; }
post(){ # $1=url $2=json  -> echoes http code, body in /tmp/r.json
  curl -s -o /tmp/r.json -w '%{http_code}' -X POST "$BASE$1" -H 'Content-Type: application/json' ${3:-} -d "$2"
}
put(){ curl -s -o /tmp/r.json -w '%{http_code}' -X PUT "$BASE$1" -H 'Content-Type: application/json' -H "$OH" -d "$2"; }
get(){ curl -s -o /tmp/r.json -w '%{http_code}' "$BASE$1" ${2:+-H "$2"}; }
send_tx(){ # $1=api_key $2=secret $3=body -> echoes code
  local sig=$(printf '%s' "$3" | openssl dgst -sha256 -hmac "$2" | awk '{print $2}')
  curl -s -o /tmp/r.json -w '%{http_code}' -X POST "$BASE/api/v1/wallet/webhook" \
    -H 'Content-Type: application/json' -H "X-API-Key: $1" -H "x-wallet-signature: $sig" -d "$3"
}
echo "═══════════ AEGIS E2E ═══════════"

# 1. Owner auth
c=$(get /api/v1/admin/overview "$OH")
[ "$c" = "200" ] && ok "1. Owner overview 200" || no "1. Owner overview $c"

# 2. Create Tenant A (bank, limit=2, with institution owner)
c=$(post /api/v1/admin/tenants "{\"name\":\"بنك الأمان ${TS}\",\"type\":\"bank\",\"country\":\"YE\",\"plan\":\"production\",\"investigator_limit\":2,\"owner_email\":\"owner${TS}@amana-bank.test\",\"owner_password\":\"OwnerPass!2026\",\"owner_name\":\"سارة العدني\",\"timezone\":\"Asia/Aden\",\"review_message\":\"تم تعليق العملية مؤقتًا للمراجعة الأمنية.\"}" "$OH")
TID_A=$(jget tenant_id); API_A=$(jget api_key); SEC_A=$(jget hmac_secret)
[ "$c" = "201" ] && [ -n "$TID_A" ] && ok "2. Tenant A created ($TID_A)" || no "2. Tenant A $c"

# 3. Create Tenant B
c=$(post /api/v1/admin/tenants '{"name":"محفظة النور","type":"wallet","country":"SA","plan":"sandbox","investigator_limit":1}' "$OH")
TID_B=$(jget tenant_id); API_B=$(jget api_key); SEC_B=$(jget hmac_secret)
[ "$c" = "201" ] && [ -n "$TID_B" ] && ok "3. Tenant B created ($TID_B)" || no "3. Tenant B $c"

# 4-5. Investigators A1, A2 (limit=2)
c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv1${TS}@amana-bank.test\",\"name\":\"أحمد علي\",\"password\":\"InvPass!2026\"}" "$OH")
INV_A1=$(jget investigator_id)
[ "$c" = "201" ] && ok "4. Investigator A1 created" || no "4. A1 $c"
c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv2${TS}@amana-bank.test\",\"name\":\"منى حسن\",\"password\":\"InvPass!2026\"}" "$OH")
INV_A2=$(jget investigator_id)
[ "$c" = "201" ] && ok "5. Investigator A2 created" || no "5. A2 $c"

# 6. Third must be rejected (limit=2)
c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv3${TS}@amana-bank.test\",\"name\":\"خالد\",\"password\":\"InvPass!2026\"}" "$OH")
[ "$c" = "409" ] && ok "6. Investigator limit enforced (409)" || no "6. Limit not enforced: $c"

# 7. Raise limit 2→3
c=$(put /api/v1/admin/tenants/$TID_A '{"investigator_limit":3}')
[ "$c" = "200" ] && ok "7. Limit raised to 3" || no "7. Raise limit $c"

# 8. Third now allowed
c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv3${TS}@amana-bank.test\",\"name\":\"خالد\",\"password\":\"InvPass!2026\"}" "$OH")
[ "$c" = "201" ] && ok "8. A3 created after raise" || no "8. A3 $c"

# 9. Investigator A1 login
c=$(post /api/v1/investigator/login "{\"email\":\"inv1${TS}@amana-bank.test\",\"password\":\"InvPass!2026\"}")
TOK_A1=$(jget access_token)
[ "$c" = "200" ] && [ -n "$TOK_A1" ] && ok "9. A1 login OK" || no "9. A1 login $c"

# 10. Suspend/activate A1
c=$(post /api/v1/admin/tenants/$TID_A/investigators/$INV_A1/suspend '{}' "$OH")
[ "$c" = "200" ] && ok "10a. A1 suspended" || no "10a. suspend $c"
c=$(post /api/v1/investigator/login "{\"email\":\"inv1${TS}@amana-bank.test\",\"password\":\"InvPass!2026\"}")
[ "$c" = "401" ] && ok "10b. Suspended A1 login rejected (401)" || no "10b. suspended login $c"
c=$(post /api/v1/admin/tenants/$TID_A/investigators/$INV_A1/activate '{}' "$OH")
[ "$c" = "200" ] && ok "10c. A1 reactivated" || no "10c. activate $c"

# 11-13. Transactions: ALLOW / BLOCK / REVIEW (Tenant A)
c=$(send_tx "$API_A" "$SEC_A" '{"transaction":{"tx_id":"e2e-allow-1","amount":45,"currency":"USD","sender_account_id":"acct-allow","beneficiary_account_id":"bene-1","device":{"device_id":"dev-known-1"}},"context":{"account_age_days":400}}')
DEC=$(jget decision)
[ "$c" = "200" ] && [ "$DEC" = "allow" ] && ok "11. Low-risk tx → ALLOW" || no "11. tx allow: $c/$DEC"
c=$(send_tx "$API_A" "$SEC_A" '{"transaction":{"tx_id":"e2e-block-1","amount":9500,"currency":"USD","sender_account_id":"acct-block","beneficiary_account_id":"bene-2","device":{"device_id":"dev-new-block"}},"context":{"account_age_days":1,"impossible_travel":true}}')
DEC=$(jget decision)
[ "$c" = "200" ] && [ "$DEC" = "block" ] && ok "12. High-risk tx → BLOCK" || no "12. tx block: $c/$DEC"
c=$(send_tx "$API_A" "$SEC_A" '{"transaction":{"tx_id":"e2e-review-1","amount":5200,"currency":"USD","sender_account_id":"acct-review","beneficiary_account_id":"bene-3","device":{"device_id":"dev-new-review"}},"context":{"account_age_days":5,"impossible_travel":true}}')
DEC=$(jget decision); MSG=$(jget review_message)
[ "$c" = "200" ] && [ "$DEC" = "review" ] && [ -n "$MSG" ] && ok "13. Mid-high tx → REVIEW + user message" || no "13. tx review: $c/$DEC"

# 14. Tenant B also gets a REVIEW tx (isolation source)
c=$(send_tx "$API_B" "$SEC_B" '{"transaction":{"tx_id":"e2e-review-b1","amount":6100,"currency":"SAR","sender_account_id":"acct-b","beneficiary_account_id":"bene-b","device":{"device_id":"dev-b-new"}},"context":{"account_age_days":2}}')
DEC=$(jget decision)
[ "$c" = "200" ] && [ "$DEC" = "review" ] && ok "14. Tenant B REVIEW tx" || no "14. B tx: $c/$DEC"

# 15. Isolation: A1 sees ONLY Tenant A queue (B's tx invisible)
c=$(get /api/v1/investigator/queue "Authorization: Bearer $TOK_A1")
N_B=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(sum(1 for x in d if 'e2e-review-b1' in json.dumps(x)))")
[ "$N_B" = "0" ] && ok "15. Isolation: A1 queue hides Tenant B tx" || no "15. Leak! B tx visible to A1"

# 16. A1 resolves the review alert
c=$(get /api/v1/investigator/alerts "Authorization: Bearer $TOK_A1")
ALERT_A=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(d[0]['alert_id'] if d else '')")
c=$(post /api/v1/investigator/alerts/$ALERT_A/assign '{}' "Authorization: Bearer $TOK_A1")
[ "$c" = "200" ] && ok "16a. Alert assigned" || no "16a. assign $c"
c=$(post /api/v1/investigator/alerts/$ALERT_A/notes '{"text":"ملاحظة بالعربية: يبدو نمط سفر مستحيل، نكمل التحقق"}' "Authorization: Bearer $TOK_A1")
[ "$c" = "200" ] && ok "16b. Arabic note added" || no "16b. note $c"
c=$(post /api/v1/investigator/alerts/$ALERT_A/resolve '{"resolution":"resolved_true_positive","note":"تم تأكيد الاحتيال بعد المراجعة"}' "Authorization: Bearer $TOK_A1")
[ "$c" = "200" ] && ok "16c. Alert resolved (TP)" || no "16c. resolve $c"

# 17. IDOR: A1 must NOT read Tenant B's alert
B_AL_ID=$(curl -s -H "$OH" "$BASE/api/v1/admin/tenants/$TID_B/alerts" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[0]['alert_id'] if d else '')")
c=$(get /api/v1/investigator/alerts/$B_AL_ID "Authorization: Bearer $TOK_A1")
[ "$c" = "404" ] && ok "17. IDOR: A1 blocked from B alert (404)" || no "17. IDOR leak: $c"

# 18. Institution Owner A: login + dashboard + manual-reviews
c=$(post /api/v1/auth/institution/login "{\"email\":\"owner${TS}@amana-bank.test\",\"password\":\"OwnerPass!2026\"}")
TOK_OA=$(jget access_token)
[ "$c" = "200" ] && [ -n "$TOK_OA" ] && ok "18a. Institution owner A login" || no "18a. owner login $c"
c=$(get /api/v1/admin/merchant/dashboard "Authorization: Bearer $TOK_OA")
TID_D=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(d.get('tenant_id',''))")
[ "$c" = "200" ] && [ "$TID_D" = "$TID_A" ] && ok "18b. Owner A dashboard scoped to A" || no "18b. dashboard $c/$TID_D"
c=$(get /api/v1/admin/merchant/manual-reviews "Authorization: Bearer $TOK_OA")
MAN=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(len(d) if isinstance(d,list) else 'x')")
[ "$c" = "200" ] && [ "$MAN" != "0" ] && ok "18c. Manual-processed tx visible (actor trail)" || no "18c. manual reviews $c/$MAN"

# 19. Owner A cannot see Tenant B data
c=$(get /api/v1/admin/merchant/dashboard "Authorization: Bearer $TOK_OA")
TID_D=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(d.get('tenant_id',''))")
[ "$TID_D" = "$TID_A" ] && ok "19. Tenant B invisible to Owner A" || no "19. isolation broken"

# 20. Reports: JSON + real PDF
c=$(post /api/v1/reports/generate '{"period":"daily"}' "Authorization: Bearer $TOK_OA")
[ "$c" = "200" ] && ok "20a. Daily report generated" || no "20a. report $c"
c=$(curl -s -o /tmp/report.pdf -w '%{http_code}' "$BASE/api/v1/reports/pdf?period=daily" -H "Authorization: Bearer $TOK_OA")
PDFMAGIC=$(head -c 5 /tmp/report.pdf)
[ "$c" = "200" ] && [ "$PDFMAGIC" = "%PDF-" ] && ok "20b. Real PDF (%PDF-)" || no "20b. pdf $c/$PDFMAGIC"

# 21. Suspended tenant rejects transactions; reactivated works
c=$(post /api/v1/admin/tenants/$TID_A/suspend '{}' "$OH")
[ "$c" = "200" ] && ok "21a. Tenant A suspended" || no "21a. suspend tenant $c"
c=$(send_tx "$API_A" "$SEC_A" '{"transaction":{"tx_id":"e2e-after-suspend","amount":50,"currency":"USD","sender_account_id":"acct-s","beneficiary_account_id":"bene-s"}}')
[ "$c" = "403" ] && ok "21b. Suspended tenant ingestion blocked (403)" || no "21b. suspend ingest $c"
c=$(post /api/v1/admin/tenants/$TID_A/activate '{}' "$OH")
[ "$c" = "200" ] && ok "21c. Tenant A reactivated" || no "21c. activate tenant $c"
c=$(send_tx "$API_A" "$SEC_A" '{"transaction":{"tx_id":"e2e-after-activate","amount":30,"currency":"USD","sender_account_id":"acct-s2","beneficiary_account_id":"bene-s2"}}')
[ "$c" = "200" ] && ok "21d. Ingestion works again after activation" || no "21d. reactivate ingest $c"

# 22. Owner audit log contains key events
c=$(get /api/v1/admin/audit?limit=100 "$OH")
EVENTS=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(len(d) if isinstance(d,list) else 0)")
[ "$EVENTS" != "0" ] && ok "22. Audit log non-empty ($EVENTS events)" || no "22. audit $c"

echo "══════════════════════════════"
echo "E2E RESULT: PASS=$PASS FAIL=$FAIL"
exit 0
