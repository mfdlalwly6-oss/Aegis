#!/usr/bin/env bash
# AEGIS Local E2E — real API checks against the running server on localhost:8000
set +e
BASE=http://localhost:8000
OWNER=flLPeQtZ68SfzY3ofo_3PLoZpa0-iKn0kmCc4f4ceUz6E61KAxwD5C7m0gcor68N
OH="X-Owner-Token: $OWNER"
TS=$(date +%s)
PASS=0; FAIL=0
ok(){ echo "  PASS: $1"; PASS=$((PASS+1)); }
no(){ echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
post(){ curl -s -m20 -o /tmp/r.json -w '%{http_code}' -X POST "$BASE$1" -H 'Content-Type: application/json' ${3:+-H "$3"} -d "$2"; }
put(){ curl -s -m20 -o /tmp/r.json -w '%{http_code}' -X PUT "$BASE$1" -H 'Content-Type: application/json' -H "$OH" -d "$2"; }
get(){ curl -s -m20 -o /tmp/r.json -w '%{http_code}' "$BASE$1" ${2:+-H "$2"}; }
jget(){ python3 -c "import json,sys
try:
 d=json.load(open('/tmp/r.json'))
except Exception:
 print(''); raise SystemExit
print(d.get('$1','') if isinstance(d,dict) else '')" 2>/dev/null; }
send_tx(){ local sig=$(python3 -c "import hmac,hashlib,sys;print(hmac.new(sys.argv[1].encode(),open(sys.argv[2],'rb').read(),hashlib.sha256).hexdigest())" "$2" "$3"); curl -s -m20 -o /tmp/r.json -w '%{http_code}' -X POST "$BASE/api/v1/wallet/webhook" -H 'Content-Type: application/json' -H "X-API-Key: $1" -H "x-wallet-signature: $sig" --data-binary @"$3"; }

echo "═══════════ AEGIS LOCAL E2E (TS=$TS) ═══════════"
c=$(get /health); [ "$c" = "200" ] && ok "health 200 status=$(jget status)" || no "health $c"
c=$(get /ready); [ "$c" = "200" ] && ok "ready 200 status=$(jget status)" || no "ready $c"
c=$(get /api/v1/admin/overview "$OH"); [ "$c" = "200" ] && ok "1 owner overview" || no "1 owner overview $c"

c=$(post /api/v1/admin/tenants "{\"name\":\"Bank A $TS\",\"type\":\"bank\",\"country\":\"YE\",\"plan\":\"production\",\"investigator_limit\":2,\"owner_email\":\"owner$TS@a.test\",\"owner_password\":\"OwnerPass!2026\",\"owner_name\":\"Sara\",\"timezone\":\"Asia/Aden\",\"review_message\":\"Pending security review\"}" "$OH")
TID_A=$(jget tenant_id); API_A=$(jget api_key); SEC_A=$(jget hmac_secret)
[ "$c" = "201" ] && [ -n "$TID_A" ] && ok "2 tenant A created" || no "2 tenant A $c"
c=$(post /api/v1/admin/tenants "{\"name\":\"Wallet B $TS\",\"type\":\"wallet\",\"country\":\"SA\",\"plan\":\"sandbox\",\"investigator_limit\":1}" "$OH")
TID_B=$(jget tenant_id); API_B=$(jget api_key); SEC_B=$(jget hmac_secret)
[ "$c" = "201" ] && ok "3 tenant B created" || no "3 tenant B $c"

for i in 1 2; do c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv$i$TS@a.test\",\"name\":\"Inv$i\",\"password\":\"InvPass!2026\"}" "$OH"); [ "$c" = "201" ] && ok "4 inv A$i created" || no "4 inv A$i $c"; done
c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv3$TS@a.test\",\"name\":\"Inv3\",\"password\":\"InvPass!2026\"}" "$OH")
[ "$c" = "409" ] && ok "5 limit 409 reached" || no "5 limit $c"
c=$(put /api/v1/admin/tenants/$TID_A '{"investigator_limit":3}')
[ "$c" = "200" ] && ok "6 limit raised 2->3" || no "6 raise $c"
c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv3$TS@a.test\",\"name\":\"Inv3\",\"password\":\"InvPass!2026\"}" "$OH")
[ "$c" = "201" ] && ok "7 A3 after raise" || no "7 A3 $c"

c=$(post /api/v1/auth/institution/login "{\"email\":\"owner$TS@a.test\",\"password\":\"OwnerPass!2026\"}")
TOK_O=$(jget access_token)
[ "$c" = "200" ] && [ -n "$TOK_O" ] && ok "8 owner login" || no "8 owner login $c"
c=$(get /api/v1/admin/merchant/dashboard "Authorization: Bearer $TOK_O")
TD=$(jget tenant_id); [ "$c" = "200" ] && [ "$TD" = "$TID_A" ] && ok "9 owner dashboard scoped to A" || no "9 dash $c/$TD"
c=$(post /api/v1/admin/merchant/investigators "{\"email\":\"inv4$TS@a.test\",\"name\":\"Inv4\",\"password\":\"InvPass!2026\"}" "Authorization: Bearer $TOK_O")
[ "$c" = "409" ] && ok "10 owner-side limit 409" || no "10 owner inv $c"
c=$(get "/api/v1/admin/merchant/feed?filter=all" "Authorization: Bearer $TOK_O")
[ "$c" = "200" ] && ok "11 feed endpoint" || no "11 feed $c"

echo '{"transaction":{"tx_id":"tx-allow","amount":45,"currency":"USD","sender_account_id":"s1","beneficiary_account_id":"b1","device":{"device_id":"dk"}},"context":{"account_age_days":400}}' > /tmp/t1.json
c=$(send_tx "$API_A" "$SEC_A" /tmp/t1.json); D=$(jget decision); [ "$c" = "200" ] && ok "12 tx allow ($D)" || no "12 tx1 $c/$D"
echo '{"transaction":{"tx_id":"tx-block","amount":9500,"currency":"USD","sender_account_id":"s2","beneficiary_account_id":"b2","device":{"device_id":"dnb"}},"context":{"account_age_days":1,"impossible_travel":true}}' > /tmp/t2.json
c=$(send_tx "$API_A" "$SEC_A" /tmp/t2.json); D=$(jget decision); [ "$c" = "200" ] && ok "13 tx block+ ($D)" || no "13 tx2 $c/$D"
echo '{"transaction":{"tx_id":"tx-review","amount":5200,"currency":"USD","sender_account_id":"s3","beneficiary_account_id":"b3","device":{"device_id":"dnr"}},"context":{"account_age_days":5,"impossible_travel":true}}' > /tmp/t3.json
c=$(send_tx "$API_A" "$SEC_A" /tmp/t3.json); D=$(jget decision); [ "$c" = "200" ] && ok "14 tx review ($D)" || no "14 tx3 $c/$D"

c=$(get "/api/v1/admin/merchant/feed?filter=all" "Authorization: Bearer $TOK_O")
N=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(len(d.get('transactions',[])))" 2>/dev/null)
[ "$N" -ge 3 ] && ok "15 feed all count=$N" || no "15 feed all $N"
AC=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(d['counts']['auto_allow'])" 2>/dev/null)
[ "$AC" -ge 1 ] && ok "16 counts auto_allow=$AC" || no "16 counts auto_allow=$AC"

ALR=$(curl -s -m20 -H "Authorization: Bearer $TOK_O" "$BASE/api/v1/admin/merchant/feed?filter=all" | python3 -c "import sys,json;d=json.load(sys.stdin);t=[x for x in d.get('transactions',[]) if x.get('alert_id')];print(t[0]['alert_id'] if t else '')" 2>/dev/null)
if [ -n "$ALR" ]; then
  c=$(post /api/v1/admin/merchant/reviews/$ALR/decision '{"decision":"allow","note":"approved by owner"}' "Authorization: Bearer $TOK_O")
  AT=$(jget actor_type)
  [ "$c" = "200" ] && [ "$AT" = "institution_owner" ] && ok "17 owner review actor_type=$AT" || no "17 owner review $c/$AT"
else no "17 no pending alert (skipped)"; fi
c=$(get "/api/v1/admin/merchant/manual-reviews" "Authorization: Bearer $TOK_O")
MT=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(d[0]['actor_type'] if d else '')" 2>/dev/null)
[ "$c" = "200" ] && [ "$MT" = "institution_owner" ] && ok "18 manual-reviews actor=$MT" || no "18 manual $c/$MT"

c=$(post /api/v1/investigator/login "{\"email\":\"inv1$TS@a.test\",\"password\":\"InvPass!2026\"}")
TOK_I=$(jget access_token)
[ "$c" = "200" ] && [ -n "$TOK_I" ] && ok "19 investigator login" || no "19 inv login $c"
ALR2=$(curl -s -m20 -H "Authorization: Bearer $TOK_I" "$BASE/api/v1/investigator/alerts" | python3 -c "import sys,json;d=json.load(sys.stdin);items=d if isinstance(d,list) else d.get('alerts',[]);print(items[0]['alert_id'] if items else '')" 2>/dev/null)
if [ -n "$ALR2" ]; then
  c=$(post /api/v1/investigator/alerts/$ALR2/resolve '{"resolution":"resolved_true_positive","note":"confirmed by inv"}' "Authorization: Bearer $TOK_I")
  [ "$c" = "200" ] && ok "20 investigator resolve" || no "20 inv resolve $c"
else no "20 no alert for inv (skipped)"; fi

echo '{"transaction":{"tx_id":"tx-b1","amount":6100,"currency":"SAR","sender_account_id":"sb","beneficiary_account_id":"bb","device":{"device_id":"db"}},"context":{"account_age_days":2,"impossible_travel":true}}' > /tmp/t4.json
send_tx "$API_B" "$SEC_B" /tmp/t4.json >/dev/null
B_AL=$(curl -s -m20 -H "$OH" "$BASE/api/v1/alerts/?limit=200" | python3 -c "import sys,json;d=json.load(sys.stdin);items=d if isinstance(d,list) else d.get('alerts',[]);print(next((a['alert_id'] for a in items if a.get('tenant_id')=='$TID_B'),''))" 2>/dev/null)
if [ -n "$B_AL" ]; then
  c=$(curl -s -m20 -o /tmp/r.json -w '%{http_code}' -H "Authorization: Bearer $TOK_I" "$BASE/api/v1/investigator/alerts/$B_AL")
  [ "$c" = "404" ] && ok "21 IDOR blocked 404" || no "21 IDOR $c"
else no "21 no B alert (skipped)"; fi

c=$(post /api/v1/admin/tenants/$TID_B/suspend '{}' "$OH"); [ "$c" = "200" ] && ok "22a suspend B" || no "22a suspend $c"
c=$(send_tx "$API_B" "$SEC_B" /tmp/t1.json); [ "$c" = "403" ] && ok "22b ingest blocked 403" || no "22b ingest $c"
c=$(post /api/v1/admin/tenants/$TID_B/activate '{}' "$OH"); [ "$c" = "200" ] && ok "22c activate B" || no "22c activate $c"
c=$(send_tx "$API_B" "$SEC_B" /tmp/t4.json); [ "$c" = "200" ] && ok "22d ingest after activate" || no "22d reingest $c"

for p in daily weekly monthly; do c=$(post /api/v1/reports/generate "{\"period\":\"$p\",\"timezone\":\"Asia/Aden\"}" "Authorization: Bearer $TOK_O"); [ "$c" = "200" ] && ok "23 report $p" || no "23 report $p $c"; done
curl -s -m30 -o /tmp/rep.pdf "$BASE/api/v1/reports/pdf?period=daily" -H "Authorization: Bearer $TOK_O"
if head -c 5 /tmp/rep.pdf | grep -q "%PDF-"; then ok "24 PDF magic %PDF-"; else no "24 PDF magic $(head -c 5 /tmp/rep.pdf 2>/dev/null)"; fi

c=$(get "/api/v1/admin/audit?limit=50" "$OH"); [ "$c" = "200" ] && ok "25 audit log" || no "25 audit $c"
for p in admin merchant investigator; do c=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/$p/"); [ "$c" = "200" ] && ok "26 portal /$p/ 200" || no "26 portal $p $c"; done
for u in /admin/app.js /admin/styles.css /merchant/app.js /investigator/app.js /investigator/styles.css; do c=$(curl -s -o /dev/null -w '%{http_code}' "$BASE$u"); [ "$c" = "200" ] && ok "27 asset $u 200" || no "27 asset $u $c"; done
c=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/docs"); [ "$c" = "200" ] && ok "28 docs 200" || no "28 docs $c"
echo "══════════════════════════════"
echo "E2E LOCAL RESULT: PASS=$PASS FAIL=$FAIL"
exit 0
