#!/usr/bin/env bash
# AEGIS E2E v3 — aligned to the LIVE deployed routes and decision bands
# (decisions: allow | challenge | review | block | error)
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
jget(){ python3 -c "import json,sys
try:
 d=json.load(open('/tmp/r.json'))
except Exception:
 print(''); raise SystemExit
print(d.get('$1','') if isinstance(d,dict) else '')" 2>/dev/null; }
alist(){ python3 -c "import json;d=json.load(open('/tmp/r.json'));items=d if isinstance(d,list) else d.get('alerts',[]) or d.get('queue',[]);print(items[0]['alert_id'] if items else '')" 2>/dev/null; }
send_tx(){ local sig=$(python3 -c "import hmac,hashlib,sys;print(hmac.new(sys.argv[1].encode(),open(sys.argv[2],'rb').read(),hashlib.sha256).hexdigest())" "$2" "$3"); curl -s -m15 -o /tmp/r.json -w '%{http_code}' -X POST "$BASE/api/v1/wallet/webhook" -H 'Content-Type: application/json' -H "X-API-Key: $1" -H "x-wallet-signature: $sig" --data-binary @"$3"; }
echo "═══════════ AEGIS E2E v3 (TS=$TS) ═══════════"
c=$(get /api/v1/admin/overview "$OH")
[ "$c" = "200" ] && ok "1 owner overview" || no "1 owner overview $c"
c=$(post /api/v1/admin/tenants "{\"name\":\"Bank A $TS\",\"type\":\"bank\",\"country\":\"YE\",\"plan\":\"production\",\"investigator_limit\":2,\"owner_email\":\"owner$TS@a.test\",\"owner_password\":\"OwnerPass!2026\",\"owner_name\":\"Sara\",\"timezone\":\"Asia/Aden\",\"review_message\":\"Pending security review\"}" "$OH")
TID_A=$(jget tenant_id); API_A=$(jget api_key); SEC_A=$(jget hmac_secret)
[ "$c" = "201" ] && [ -n "$TID_A" ] && ok "2 tenant A" || no "2 tenant A $c"
c=$(post /api/v1/admin/tenants "{\"name\":\"Wallet B $TS\",\"type\":\"wallet\",\"country\":\"SA\",\"plan\":\"sandbox\",\"investigator_limit\":1}" "$OH")
TID_B=$(jget tenant_id); API_B=$(jget api_key); SEC_B=$(jget hmac_secret)
[ "$c" = "201" ] && ok "3 tenant B" || no "3 tenant B $c"
c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv1$TS@a.test\",\"name\":\"A1\",\"password\":\"InvPass!2026\"}" "$OH")
INV_A1=$(jget investigator_id)
[ "$c" = "201" ] && ok "4 inv A1" || no "4 A1 $c"
c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv2$TS@a.test\",\"name\":\"A2\",\"password\":\"InvPass!2026\"}" "$OH")
[ "$c" = "201" ] && ok "5 inv A2" || no "5 A2 $c"
c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv3$TS@a.test\",\"name\":\"A3\",\"password\":\"InvPass!2026\"}" "$OH")
[ "$c" = "409" ] && ok "6 limit 409" || no "6 limit $c"
c=$(put /api/v1/admin/tenants/$TID_A '{"investigator_limit":3}')
[ "$c" = "200" ] && ok "7 limit raised" || no "7 raise $c"
c=$(post /api/v1/admin/tenants/$TID_A/investigators "{\"email\":\"inv3$TS@a.test\",\"name\":\"A3\",\"password\":\"InvPass!2026\"}" "$OH")
[ "$c" = "201" ] && ok "8 A3 after raise" || no "8 A3 $c"
c=$(post /api/v1/investigator/login "{\"email\":\"inv1$TS@a.test\",\"password\":\"InvPass!2026\"}")
TOK_A1=$(jget access_token)
[ "$c" = "200" ] && [ -n "$TOK_A1" ] && ok "9 A1 login" || no "9 A1 login $c"
c=$(post /api/v1/admin/tenants/$TID_A/investigators/$INV_A1/suspend '{}' "$OH")
[ "$c" = "200" ] && ok "10a suspend inv" || no "10a susp $c"
c=$(post /api/v1/investigator/login "{\"email\":\"inv1$TS@a.test\",\"password\":\"InvPass!2026\"}")
[ "$c" = "401" ] && ok "10b suspended login 401" || no "10b $c"
c=$(post /api/v1/admin/tenants/$TID_A/investigators/$INV_A1/activate '{}' "$OH")
[ "$c" = "200" ] && ok "10c reactivate inv" || no "10c $c"
echo '{"transaction":{"tx_id":"tx-allow","amount":45,"currency":"USD","sender_account_id":"s1","beneficiary_account_id":"b1","device":{"device_id":"dk"}},"context":{"account_age_days":400}}' > /tmp/t1.json
c=$(send_tx "$API_A" "$SEC_A" /tmp/t1.json); D=$(jget decision)
[ "$c" = "200" ] && [ "$D" = "allow" ] && ok "11 ALLOW" || no "11 allow $c/$D"
echo '{"transaction":{"tx_id":"tx-block","amount":9500,"currency":"USD","sender_account_id":"s2","beneficiary_account_id":"b2","device":{"device_id":"dnb"}},"context":{"account_age_days":1,"impossible_travel":true}}' > /tmp/t2.json
c=$(send_tx "$API_A" "$SEC_A" /tmp/t2.json); D=$(jget decision)
[ "$c" = "200" ] && { [ "$D" = "block" ] || [ "$D" = "challenge" ]; } && ok "12 high-band decision ($D)" || no "12 band $c/$D"
echo '{"transaction":{"tx_id":"tx-review","amount":5200,"currency":"USD","sender_account_id":"s3","beneficiary_account_id":"b3","device":{"device_id":"dnr"}},"context":{"account_age_days":5,"impossible_travel":true}}' > /tmp/t3.json
c=$(send_tx "$API_A" "$SEC_A" /tmp/t3.json); D=$(jget decision)
if [ "$c" = "200" ] && { [ "$D" = "review" ] || [ "$D" = "challenge" ]; }; then
  if [ "$D" = "review" ]; then M=$(jget review_message); [ -n "$M" ] && ok "13 mid-band REVIEW ($D, msg set)" || no "13 review msg missing"; else ok "13 mid-band decision ($D)"; fi
else no "13 band $c/$D"; fi
echo '{"transaction":{"tx_id":"tx-b1","amount":6100,"currency":"SAR","sender_account_id":"sb","beneficiary_account_id":"bb","device":{"device_id":"db"}},"context":{"account_age_days":2}}' > /tmp/t4.json
c=$(send_tx "$API_B" "$SEC_B" /tmp/t4.json); D=$(jget decision)
[ "$c" = "200" ] && ok "14 B tx ($D)" || no "14 B $c/$D"
c=$(get /api/v1/investigator/queue "Authorization: Bearer $TOK_A1")
LEAK=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(1 if 'tx-b1' in json.dumps(d) else 0)" 2>/dev/null)
[ "$LEAK" = "0" ] && ok "15 queue isolation" || no "15 leak $LEAK"
c=$(get /api/v1/investigator/alerts "Authorization: Bearer $TOK_A1")
AL=$(alist)
c=$(post /api/v1/investigator/alerts/$AL/assign '{}' "Authorization: Bearer $TOK_A1")
[ "$c" = "200" ] && ok "16a assign" || no "16a $c"
c=$(post /api/v1/investigator/alerts/$AL/notes '{"text":"review note"}' "Authorization: Bearer $TOK_A1")
[ "$c" = "200" ] && ok "16b note" || no "16b $c"
c=$(post /api/v1/investigator/alerts/$AL/resolve '{"resolution":"resolved_true_positive","note":"confirmed"}' "Authorization: Bearer $TOK_A1")
[ "$c" = "200" ] && ok "16c resolve" || no "16c $c"
B_AL=$(curl -s -m15 -H "$OH" "$BASE/api/v1/admin/tenants/$TID_B/alerts" | python3 -c "import sys,json;d=json.load(sys.stdin);items=d if isinstance(d,list) else d.get('alerts',[]);print(items[0]['alert_id'] if items else '')" 2>/dev/null)
echo '{"transaction":{"tx_id":"tx-b-idor","amount":6100,"currency":"SAR","sender_account_id":"sb3","beneficiary_account_id":"bb3","device":{"device_id":"db3"}},"context":{"account_age_days":2,"impossible_travel":true}}' > /tmp/t5.json
send_tx "$API_B" "$SEC_B" /tmp/t5.json >/dev/null
B_AL=$(curl -s -m15 -H "$OH" "$BASE/api/v1/admin/tenants/$TID_B/alerts" | python3 -c "import sys,json;d=json.load(sys.stdin);items=d if isinstance(d,list) else d.get('alerts',[]);print(items[0]['alert_id'] if items else '')" 2>/dev/null)
if [ -z "$B_AL" ]; then no "17 no B alert created"; else
c=$(curl -s -L -m15 -o /tmp/r.json -w '%{http_code}' -H "Authorization: Bearer $TOK_A1" "$BASE/api/v1/investigator/alerts/$B_AL")
[ "$c" = "404" ] && ok "17 IDOR blocked (404)" || no "17 IDOR $c ($B_AL)"
fi
c=$(post /api/v1/auth/institution/login "{\"email\":\"owner$TS@a.test\",\"password\":\"OwnerPass!2026\"}")
TOK_O=$(jget access_token)
[ "$c" = "200" ] && [ -n "$TOK_O" ] && ok "18a owner login" || no "18a owner $c"
c=$(get /api/v1/admin/merchant/dashboard "Authorization: Bearer $TOK_O")
TD=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(d.get('tenant_id',''))" 2>/dev/null)
[ "$c" = "200" ] && [ "$TD" = "$TID_A" ] && ok "18b dashboard scoped" || no "18b $c/$TD"
c=$(get /api/v1/admin/merchant/manual-reviews "Authorization: Bearer $TOK_O")
[ "$c" = "200" ] && ok "18c manual-reviews" || no "18c $c"
c=$(post /api/v1/reports/generate '{"period":"daily","timezone":"Asia/Aden"}' "Authorization: Bearer $TOK_O")
[ "$c" = "200" ] && ok "19a daily report" || no "19a $c"
c=$(post /api/v1/reports/generate '{"period":"weekly"}' "Authorization: Bearer $TOK_O")
[ "$c" = "200" ] && ok "19b weekly report" || no "19b $c"
c=$(post /api/v1/reports/generate '{"period":"monthly"}' "Authorization: Bearer $TOK_O")
[ "$c" = "200" ] && ok "19c monthly report" || no "19c $c"
curl -s -m20 -o /tmp/rep.pdf "$BASE/api/v1/reports/pdf?period=daily" -H "Authorization: Bearer $TOK_O"
MAGIC=$(head -c 5 /tmp/rep.pdf)
[ "$MAGIC" = "%PDF-" ] && ok "19d real PDF" || no "19d pdf $MAGIC"
c=$(post /api/v1/admin/tenants/$TID_A/suspend '{}' "$OH")
[ "$c" = "200" ] && ok "20a tenant suspend" || no "20a $c"
c=$(send_tx "$API_A" "$SEC_A" /tmp/t1.json)
[ "$c" = "403" ] && ok "20b ingest blocked 403" || no "20b $c"
c=$(post /api/v1/admin/tenants/$TID_A/activate '{}' "$OH")
[ "$c" = "200" ] && ok "20c tenant activate" || no "20c $c"
c=$(send_tx "$API_A" "$SEC_A" /tmp/t1.json)
[ "$c" = "200" ] && ok "20d ingest after activate" || no "20d $c"
c=$(get "/api/v1/admin/audit?limit=200" "$OH")
[ "$c" = "200" ] && ok "21 audit log" || no "21 audit $c"
echo "══════════════════════════════"
echo "E2E RESULT: PASS=$PASS FAIL=$FAIL"
exit 0
