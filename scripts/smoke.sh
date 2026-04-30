#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://localhost}"
USERNAME="${USERNAME:-admin}"
PASSWORD="${PASSWORD:-SuperSecret123}"

echo "[smoke] healthz"
curl -fsS "$BASE/healthz" | grep -q '"ok"'

echo "[smoke] login"
TOKEN=$(curl -fsS -X POST "$BASE/api/v1/auth/login" \
    -H "content-type: application/x-www-form-urlencoded" \
    --data-urlencode "username=$USERNAME" --data-urlencode "password=$PASSWORD" \
    | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "got token: ${TOKEN:0:20}..."

echo "[smoke] create application"
curl -fsS -X POST "$BASE/api/v1/applications" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"name":"smoke-app"}' >/dev/null || true

echo "[smoke] register service"
curl -fsS -X POST "$BASE/api/v1/services" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"slug":"smoke-svc","display_name":"Smoke","endpoint_url":"http://httpbin.org/anything"}' >/dev/null || true

echo "[smoke] issue api key"
APIKEY=$(curl -fsS -X POST "$BASE/api/v1/api-keys" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"name":"smoke","owner_type":"application","owner_id":1}' \
    | python -c "import sys,json; print(json.load(sys.stdin)['plaintext'])")
echo "got api key: ${APIKEY:0:12}..."

echo "[smoke] proxy through gateway"
curl -fsS -X POST "$BASE/mcp/smoke-svc" \
    -H "Authorization: Bearer $APIKEY" -H "content-type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' >/dev/null

echo "[smoke] query call logs"
curl -fsS "$BASE/api/v1/call-logs?limit=5" \
    -H "Authorization: Bearer $TOKEN" | python -m json.tool | head -20

echo "[smoke] OK"
