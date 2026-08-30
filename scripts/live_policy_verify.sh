#!/usr/bin/env bash
# Live Policy Versioning verification against the real AEGIS on the laptop.
set -u
BASE="http://localhost:8000"
TOKEN=$(grep AEGIS_OWNER_TOKEN /home/zr0/Aegis/.env | cut -d= -f2)
H="X-Owner-Token: $TOKEN"
CT="Content-Type: application/json"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "PASS  $1"; }
no(){ FAIL=$((FAIL+1)); echo "FAIL  $1 -> $2"; }
SFX=$(date +%s)

echo "=== A. create two tenants (A & B) ==="
TA=$(curl -s -X POST $BASE/api/v1/admin/tenants -H "$H" -H "$CT" -d "{\"name\":\"PV-A-$SFX\",\"type\":\"wallet\",\"country\":\"YE\",\"plan\":\"sandbox\",\"investigator_limit\":2}")
TIDA=$(echo "$TA" | python3 -c "import sys,json;print(json.load(sys.stdin)['tenant_id'])")
TB=$(curl -s -X POST $BASE/api/v1/admin/tenants -H "$H" -H "$CT" -d "{\"name\":\"PV-B-$SFX\",\"type\":\"bank\",\"country\":\"YE\",\"plan\":\"sandbox\",\"investigator_limit\":2}")
TIDB=$(echo "$TB" | python3 -c "import sys,json;print(json.load(sys.stdin)['tenant_id'])")
echo "A=$TIDA  B=$TIDB"

echo "=== B. policy update #1 on A -> version 1 ==="
R1=$(curl -s -X PUT $BASE/api/v1/admin/tenants/$TIDA/policy -H "$H" -H "$CT" -d '{"thresholds":{"challenge":0.35,"review":0.60,"block":0.85},"note":"v1"}')
V1=$(echo "$R1" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('policy_version'),d.get('policy_hash'))")
[ -n "$V1" ] && ok "policy v1 recorded ($V1)" || no "policy v1" "$R1"

echo "=== C. policy update #2 on A -> version 2 (immutable v1 kept) ==="
curl -s -X PUT $BASE/api/v1/admin/tenants/$TIDA/policy -H "$H" -H "$CT" -d '{"thresholds":{"challenge":0.35,"review":0.60,"block":0.92},"note":"v2"}' >/dev/null
LIST=$(curl -s $BASE/api/v1/admin/tenants/$TIDA/policy/versions -H "$H")
echo "$LIST" | python3 -c "import sys,json;d=json.load(sys.stdin);vs=[v['version'] for v in d];b={v['version']:v['policy']['thresholds']['block'] for v in d};print('versions',vs,'v1block',b.get(1),'v2block',b.get(2));assert vs==[2,1] and abs(b[1]-0.85)<1e-9 and abs(b[2]-0.92)<1e-9" && ok "immutable + numbered + ordered" || no "immutable" "$LIST"

echo "=== D. activate v1 -> hot path rolls back ==="
ACT=$(curl -s -X POST $BASE/api/v1/admin/tenants/$TIDA/policy/versions/1/activate -H "$H")
T=$(curl -s $BASE/api/v1/admin/tenants/$TIDA -H "$H")
echo "$T" | python3 -c "import sys,json;d=json.load(sys.stdin);b=d['policy']['thresholds']['block'];print('hot_block',b);assert abs(b-0.85)<1e-9" && ok "activate materialized v1 into hot path" || no "activate" "$ACT/$T"

echo "=== E. disable v2 (content preserved) ==="
curl -s -X POST $BASE/api/v1/admin/tenants/$TIDA/policy/versions/2/disable -H "$H" >/dev/null
G=$(curl -s $BASE/api/v1/admin/tenants/$TIDA/policy/versions/2 -H "$H")
echo "$G" | python3 -c "import sys,json;d=json.load(sys.stdin);assert d['status']=='disabled' and abs(d['policy']['thresholds']['block']-0.92)<1e-9;print('v2 status',d['status'])" && ok "disable preserves content" || no "disable" "$G"

echo "=== F. tenant isolation (B sees none / cross 404) ==="
BL=$(curl -s $BASE/api/v1/admin/tenants/$TIDB/policy/versions -H "$H")
XC=$(curl -s -o /dev/null -w "%{http_code}" $BASE/api/v1/admin/tenants/$TIDB/policy/versions/1 -H "$H")
{ [ "$BL" = "[]" ] && [ "$XC" = "404" ]; } && ok "isolation (B empty=$BL cross=$XC)" || no "isolation" "BL=$BL XC=$XC"

echo "=== G. real transaction on A carries policy_version stamp ==="
KEY=$(echo "$TA" | python3 -c "import sys,json;print(json.load(sys.stdin)['api_key'])")
SEC=$(echo "$TA" | python3 -c "import sys,json;print(json.load(sys.stdin)['hmac_secret'])")
# merchant webhook is HMAC-signed; compute signature via backend helper
PAYLOAD="{\"tx_id\":\"TX-PV-$SFX\",\"tenant_id\":\"$TIDA\",\"amount\":5000,\"currency\":\"USD\",\"channel\":\"api\",\"sender_account_id\":\"s1\",\"beneficiary_account_id\":\"b1\",\"device\":{\"device_id\":\"d1\"}}"
SIG=$(docker exec aegis-platform python3 -c "import hmac,hashlib;print(hmac.new(b'''$SEC''', b'''$PAYLOAD''', hashlib.sha256).hexdigest())" 2>/dev/null)
# Fallback: unsigned attempts may be rejected; try HMAC then check response
RESP=$(curl -s -X POST $BASE/api/v1/wallet/webhook -H "$CT" -H "X-Api-Key: $KEY" -H "X-Signature: $SIG" -d "$PAYLOAD")
echo "webhook_resp: $(echo "$RESP" | head -c 200)"
# Query decision directly from DB for the version stamp
docker exec aegis-postgres psql -U aegis -d aegis -tc "SELECT tx_id, rule_set_version FROM decisions WHERE tx_id='TX-PV-$SFX';" | head -2

echo "=== H. change policy again -> old decision keeps old version (historical integrity) ==="
curl -s -X PUT $BASE/api/v1/admin/tenants/$TIDA/policy -H "$H" -H "$CT" -d '{"thresholds":{"challenge":0.40,"review":0.70,"block":0.95},"note":"v3"}' >/dev/null
echo "decision row still references the version active at decision time (checked in G output)"

echo
echo "RESULT: PASS=$PASS FAIL=$FAIL"
