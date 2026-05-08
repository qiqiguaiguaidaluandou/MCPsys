#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://localhost:8088}"
USERNAME="${USERNAME:-admin}"
PASSWORD="${PASSWORD:-admin123}"

echo "[smoke] healthz"
curl -fsS "$BASE/healthz" | grep -q '"ok"'

echo "[smoke] login"
TOKEN=$(curl -fsS -X POST "$BASE/api/v1/auth/login" \
    -H "content-type: application/x-www-form-urlencoded" \
    --data-urlencode "username=$USERNAME" --data-urlencode "password=$PASSWORD" \
    | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "got token: ${TOKEN:0:20}..."

echo "[smoke] create application (idempotent)"
curl -fsS -X POST "$BASE/api/v1/applications" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"name":"smoke-app"}' >/dev/null || true

# Look up smoke-app's id by name (works on fresh OR existing DB)
APP_ID=$(curl -fsS "$BASE/api/v1/applications" -H "Authorization: Bearer $TOKEN" \
    | python -c "import sys,json; apps=json.load(sys.stdin)['items']; print(next(a['id'] for a in apps if a['name']=='smoke-app'))")
echo "smoke-app id: $APP_ID"

echo "[smoke] register service (idempotent)"
curl -fsS -X POST "$BASE/api/v1/services" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"slug":"smoke-svc","display_name":"Smoke","endpoint_url":"http://httpbin.org/anything"}' >/dev/null || true

echo "[smoke] issue api key for app $APP_ID"
APIKEY=$(curl -fsS -X POST "$BASE/api/v1/api-keys" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d "{\"name\":\"smoke\",\"owner_type\":\"application\",\"owner_id\":$APP_ID}" \
    | python -c "import sys,json; print(json.load(sys.stdin)['plaintext'])")
echo "got api key: ${APIKEY:0:12}..."

echo "[smoke] (negative) call before grant — expect 403"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/mcp/smoke-svc" \
    -H "Authorization: Bearer $APIKEY" -H "content-type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}')
test "$HTTP" = "403" || { echo "expected 403 got $HTTP"; exit 1; }

echo "[smoke] grant permission smoke-app → smoke-svc"
curl -fsS -X POST "$BASE/api/v1/services/smoke-svc/permissions" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d "{\"application_id\":$APP_ID}" >/dev/null

echo "[smoke] proxy through gateway"
curl -fsS -X POST "$BASE/mcp/smoke-svc" \
    -H "Authorization: Bearer $APIKEY" -H "content-type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' >/dev/null

echo "[smoke] set service rate_limit_qps=1"
curl -fsS -X PATCH "$BASE/api/v1/services/smoke-svc" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"rate_limit_qps":1}' >/dev/null

echo "[smoke] burst 3 — expect at least one 429"
SUCC=0; THR=0
for i in 1 2 3; do
    H=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/mcp/smoke-svc" \
        -H "Authorization: Bearer $APIKEY" -H "content-type: application/json" \
        -d '{"jsonrpc":"2.0","method":"tools/list","id":'$i'}')
    case $H in
        200) SUCC=$((SUCC+1));;
        429) THR=$((THR+1));;
        *) echo "unexpected $H"; exit 1;;
    esac
done
echo "200=$SUCC 429=$THR"
test "$THR" -ge 1 || { echo "expected at least 1 throttled"; exit 1; }

echo "[smoke] reset rate_limit_qps to null"
curl -fsS -X PATCH "$BASE/api/v1/services/smoke-svc" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"rate_limit_qps":null}' >/dev/null

echo "[smoke] query call logs"
curl -fsS "$BASE/api/v1/call-logs?limit=5" \
    -H "Authorization: Bearer $TOKEN" | python -m json.tool | head -20

echo "[smoke] OK"
