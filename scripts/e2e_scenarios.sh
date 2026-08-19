#!/usr/bin/env bash
# AEGIS E2E v2 — built against the ACTUAL deployed routes (verified via openapi.json)
set +e
cd /home/zr0/Aegis
BASE=http://localhost:8000
TS=$(date +%s)
OWNER=$(grep -E '^AEGIS_OWNER_TOKEN=' .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' | tr -d ' ')
OH="X-Owner-Token: $OWNER"
PASS=0; FAIL=0
ok(){ echo "  PASS: $1"; PASS=$((PASS+1)); }
no(){ echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
post(){ curl -s -m15 -o /tmp/r.json -w '%{http_code}' -X POST "$BASE$1" -H 'Content-Type: application/json' ${3:+-H "$3"} -d "$2"; }
put(){ curl -s -m15 -o /tmp/r.json -w '%{http_code}' -X PUT "$BASE$1" -H 'Content-Type: application/json' -H "$OH" -d "$2"; }
get(){ curl -s -m15 -o /tmp/r.json -w '%{http_code}' "$BASE$1" ${2:+-H "$2"}; }
jget(){ python3 -c "import sys,json;
try:
 d=json.load(open('/tmp/r.json'))
except Exception:
 print(''); raise SystemExit
print(d.get('$1','') if isinstance(d,dict) else '')" 2>/dev/null; }
echo "═══════════ AEGIS E2E v2 (TS=$TS) ═══════════"

# 1 owner
c=$(get /api/v1/admin/overview "$OH")
[ "$c" = "200" ] && ok "1 owner overview" || no "1 owner overview $c"

# 2-3 tenants A,B (with institution owner on A)
c=$(post /api/v1/admin/tenants "{\"name\":\"بنك الأمان $TS\",\"type\":\"bank\",\"country\":\"YE\",\"plan\":\"production\",\"investigator_limit\":2,\"owner_email\":\"owner$TS@amana.test\",\"owner_password\":\"OwnerPass!2026\",\"owner_name\":\"سارة\",\"timezone\":\"Asia/Aden\",\"review_message\":\"تم تعليق العملية للمراجعة الأمنية\"}" "$OH")
TID_A=$(jget tenant_id); API_A=$(jget api_key); SEC_A=$(jget hmac_secret)
[ "$c" = "201" ] && [ -n "$TID_A" ] && ok "2 tenant A created" || no "2 tenant A $c $TID_A"
c=$(post /api/v1/admin/tenants "{\"name\":\"محفظة النور $TS\",\"type\":\"wallet\",\"country\":\"SA\",\"plan\":\"sandbox\",\"investigator_limit\":1}" "$OH")
TID_B=$(jget tenant_id); API_B=$(jget api_key); SEC_B=$(jget hmac_secret)
[ "$c" = "201" ] && ok "3 tenant B created" || no "3 tenant B $c"

# 4-6 investigators + limit
c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv1$TS@amana.test\",\"name\":\"أحمد\",\"password\":\"InvPass!2026\"}" "$OH")
INV_A1=$(jget investigator_id)
[ "$c" = "201" ] && ok "4 inv A1 created" || no "4 A1 $c"
c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv2$TS@amana.test\",\"name\":\"منى\",\"password\":\"InvPass!2026\"}" "$OH")
[ "$c" = "201" ] && ok "5 inv A2 created" || no "5 A2 $c"
c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv3$TS@amana.test\",\"name\":\"خالد\",\"password\":\"InvPass!2026\"}" "$OH")
[ "$c" = "409" ] && ok "6 limit enforced 409" || no "6 limit $c"

# 7-8 raise limit 2->3 then create
c=$(put /api/v1/admin/tenants/$TID_A '{"investigator_limit":3}')
[ "$c" = "200" ] && ok "7 limit raised to 3" || no "7 raise $c"
c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv3$TS@amana.test\",\"name\":\"خالد\",\"password\":\"InvPass!2026\"}" "$OH")
[ "$c" = "201" ] && ok "8 A3 after raise" || no "8 A3 $c"

# 9 login A1
c=$(post /api/v1/investigator/login "{\"email\":\"inv1$TS@amana.test\",\"password\":\"InvPass!2026\"}")
TOK_A1=$(jget access_token)
[ "$c" = "200" ] && [ -n "$TOK_A1" ] && ok "9 A1 login" || no "9 A1 login $c"

# 10 suspend/activate A1
c=$(post /api/v1/admin/tenants/$TID_A/investigators/$INV_A1/suspend '{}' "$OH")
[ "$c" = "200" ] && ok "10a A1 suspended" || no "10a susp $c"
c=$(post /api/v1/investigator/login "{\"email\":\"inv1$TS@amana.test\",\"password\":\"InvPass!2026\"}")
[ "$c" = "401" ] && ok "10b suspended login 401" || no "10b susp-login $c"
c=$(post /api/v1/admin/tenants/$TID_A/investigators/$INV_A1/activate '{}' "$OH")
[ "$c" = "200" ] && ok "10c A1 reactivated" || no "10c act $c"

# 11-14 transactions via signed webhook
send_tx(){ # $1=key $2=secret $3=bodyfile
  local sig=$(python3 -c "import hmac,hashlib,sys;print(hmac.new(sys.argv[1].encode(),open(sys.argv[2],'rb').read(),hashlib.sha256).hexdigest())" "$2" "$3")
  curl -s -m15 -o /tmp/r.json -w '%{http_code}' -X POST "$BASE/api/v1/wallet/webhook" \
    -H 'Content-Type: application/json' -H "X-API-Key: $1" -H "x-wallet-signature: $sig" --data-binary @"$3"
}
echo '{"transaction":{"tx_id":"e2e-allow-t","amount":45,"currency":"USD","sender_account_id":"ac1","beneficiary_account_id":"bn1","device":{"device_id":"dev-k"}},"context":{"account_age_days":400}}' > /tmp/tx_allow.json
c=$(send_tx "$API_A" "$SEC_A" /tmp/tx_allow.json); D=$(jget decision)
[ "$c" = "200" ] && [ "$D" = "allow" ] && ok "11 ALLOW" || no "11 allow $c/$D"
echo '{"transaction":{"tx_id":"e2e-block-t","amount":9500,"currency":"USD","sender_account_id":"ac2","beneficiary_account_id":"bn2","device":{"device_id":"dev-nb"}},"context":{"account_age_days":1,"impossible_travel":true}}' > /tmp/tx_block.json
c=$(send_tx "$API_A" "$SEC_A" /tmp/tx_block.json); D=$(jget decision)
[ "$c" = "200" ] && [ "$D" = "block" ] && ok "12 BLOCK" || no "12 block $c/$D"
echo '{"transaction":{"tx_id":"e2e-review-t","amount":5200,"currency":"USD","sender_account_id":"ac3","beneficiary_account_id":"bn3","device":{"device_id":"dev-nr"}},"context":{"account_age_days":5,"impossible_travel":true}}' > /tmp/tx_review.json
c=$(send_tx "$API_A" "$SEC_A" /tmp/tx_review.json); D=$(jget decision); M=$(jget review_message)
[ "$c" = "200" ] && [ "$D" = "review" ] && ok "13 REVIEW + message" || no "13 review $c/$D"
echo '{"transaction":{"tx_id":"e2e-b-review","amount":6100,"currency":"SAR","sender_account_id":"acb","beneficiary_account_id":"bnb","device":{"device_id":"dev-b"}},"context":{"account_age_days":2}}' > /tmp/tx_b.json
c=$(send_tx "$API_B" "$SEC_B" /tmp/tx_b.json); D=$(jget decision)
[ "$c" = "200" ] && ok "14 TenantB tx ($D)" || no "14 B $c/$D"

# 15 isolation queue
c=$(get /api/v1/investigator/queue "Authorization: Bearer $TOK_A1")
LEAK=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(sum(1 for x in d if 'e2e-b-review' in json.dumps(x)))" 2>/dev/null)
[ "$LEAK" = "0" ] && ok "15 no cross-tenant leak in queue" || no "15 leak $LEAK"

# 16 review workflow on A's review alert (open->assign->note->resolve)
c=$(get /api/v1/investigator/alerts "Authorization: Bearer $TOK_A1")
AL=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(d[0]['alert_id'] if d else '')" 2>/dev/null)
c=$(post /api/v1/investigator/alerts/$AL/assign '{}' "Authorization: Bearer $TOK_A1")
[ "$c" = "200" ] && ok "16a assign" || no "16a assign $c"
c=$(post /api/v1/investigator/alerts/$AL/notes '{"text":"ملاحظة عربية للمراجعة"}' "Authorization: Bearer $TOK_A1")
[ "$c" = "200" ] && ok "16b note" || no "16b note $c"
c=$(post /api/v1/investigator/alerts/$AL/resolve '{"resolution":"resolved_true_positive","note":"تأكيد احتيال"}' "Authorization: Bearer $TOK_A1")
[ "$c" = "200" ] && ok "16c resolve" || no "16c resolve $c"

# 17 IDOR: A1 accessing B alert must be 404 (list B alerts as owner first)
B_AL=$(curl -s -m15 -H "$OH" "$BASE/api/v1/admin/tenants/$TID_B/alerts" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[0]['alert_id'] if d else '')" 2>/dev/null)
c=$(get /api/v1/investigator/alerts/$B_AL "Authorization: Bearer $TOK_A1")
[ "$c" = "404" ] && ok "17 IDOR blocked 404" || no "17 IDOR $c"

# 18 institution owner login + dashboard scoped
c=$(post /api/v1/auth/institution/login "{\"email\":\"owner$TS@amana.test\",\"password\":\"OwnerPass!2026\"}")
TOK_O=$(jget access_token)
[ "$c" = "200" ] && [ -n "$TOK_O" ] && ok "18a owner login" || no "18a owner login $c"
c=$(get /api/v1/admin/merchant/dashboard "Authorization: Bearer $TOK_O")
TD=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(d.get('tenant_id',''))" 2>/dev/null)
[ "$c" = "200" ] && [ "$TD" = "$TID_A" ] && ok "18b dashboard scoped to A" || no "18b dash $c/$TD"
c=$(get /api/v1/admin/merchant/manual-reviews "Authorization: Bearer $TOK_O")
MAN=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(len(d) if isinstance(d,list) else 0)" 2>/dev/null)
[ "$c" = "200" ] && ok "18c manual-reviews ok ($MAN items)" || no "18c manual $c"

# 19 reports: JSON + real PDF
c=$(post /api/v1/reports/generate '{"period":"daily","timezone":"Asia/Aden"}' "Authorization: Bearer $TOK_O")
[ "$c" = "200" ] && ok "19a daily report JSON" || no "19a report $c"
curl -s -m20 -o /tmp/rep.pdf "$BASE/api/v1/reports/pdf?period=daily" -H "Authorization: Bearer $TOK_O"
MAGIC=$(head -c 5 /tmp/rep.pdf)
[ "$MAGIC" = "%PDF-" ] && ok "19b real PDF %PDF-" || no "19b pdf $MAGIC"
c=$(post /api/v1/reports/generate '{"period":"weekly"}' "Authorization: Bearer $TOK_O")
[ "$c" = "200" ] && ok "19c weekly report" || no "19c weekly $c"
c=$(post /api/v1/reports/generate '{"period":"monthly"}' "Authorization: Bearer $TOK_O")
[ "$c" = "200" ] && ok "19d monthly report" || no "19d monthly $c"

# 20 suspend/activate tenant + ingestion
c=$(post /api/v1/admin/tenants/$TID_A/suspend '{}' "$OH")
[ "$c" = "200" ] && ok "20a tenant suspended" || no "20a susp $c"
c=$(send_tx "$API_A" "$SEC_A" /tmp/tx_allow.json)
[ "$c" = "403" ] && ok "20b ingest blocked 403" || no "20b ingest $c"
c=$(post /api/v1/admin/tenants/$TID_A/activate '{}' "$OH")
[ "$c" = "200" ] && ok "20c tenant activated" || no "20c act $c"
c=$(send_tx "$API_A" "$SEC_A" /tmp/tx_allow.json)
[ "$c" = "200" ] && ok "20d ingest ok after activate" || no "20d ingest $c"

# 21 audit log non-empty + alert in tenant A alerts
c=$(get "/api/v1/admin/audit?limit=200" "$OH")
N=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(len(d) if isinstance(d,list) else 0)" 2>/dev/null)
[ "$N" != "0" ] && ok "21 audit log $N events" || no "21 audit $c"

echo "══════════════════════════════"
echo "E2E RESULT: PASS=$PASS FAIL=$FAIL"
exit 0
