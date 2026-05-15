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

# 任何方式退出都把 smoke-svc 的 QPS 复位到 null：避免上一次跑中段挂掉
# 留下 rate_limit_qps=1，下一次 PATCH 1→1 是 no-op、不广播 service:invalidate，
# 桶里又攒满 token，让「burst 3 → 期望 429」假阴性。
cleanup() {
    if [ -n "${TOKEN:-}" ]; then
        curl -fsS -X PATCH "$BASE/api/v1/services/smoke-svc" \
            -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
            -d '{"rate_limit_qps":null}' >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

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

# Look up smoke-svc id for use in service_ids payload
SVC_ID=$(curl -fsS "$BASE/api/v1/services/smoke-svc" -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "smoke-svc id: $SVC_ID"

echo "[smoke] issue api key for app $APP_ID"
APIKEY=$(curl -fsS -X POST "$BASE/api/v1/api-keys" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d "{\"name\":\"smoke\",\"application_id\":$APP_ID}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['plaintext'])")
echo "got api key: ${APIKEY:0:12}..."

echo "[smoke] (idempotent) clear smoke-app service_ids to start from default-deny"
curl -fsS -X PATCH "$BASE/api/v1/applications/$APP_ID" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"service_ids":[]}' >/dev/null

echo "[smoke] (negative) call before grant — expect 403"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/mcp/smoke-svc" \
    -H "Authorization: Bearer $APIKEY" -H "content-type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}')
test "$HTTP" = "403" || { echo "expected 403 got $HTTP"; exit 1; }

echo "[smoke] grant by setting smoke-app service_ids=[$SVC_ID]"
curl -fsS -X PATCH "$BASE/api/v1/applications/$APP_ID" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d "{\"service_ids\":[$SVC_ID]}" >/dev/null

# Verify the app-side view reflects the grant
GRANTED=$(curl -fsS "$BASE/api/v1/applications/$APP_ID" -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json; print(','.join(str(i) for i in json.load(sys.stdin)['service_ids']))")
test "$GRANTED" = "$SVC_ID" || { echo "expected service_ids=[$SVC_ID] got [$GRANTED]"; exit 1; }

echo "[smoke] proxy through gateway"
curl -fsS -X POST "$BASE/mcp/smoke-svc" \
    -H "Authorization: Bearer $APIKEY" -H "content-type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' >/dev/null

# 先 null 再设 1，保证这次 PATCH 真的是状态变化（否则 1→1 是 no-op，
# 控制面可能不广播 service:invalidate，gateway 桶里又攒满 token，burst 假阴性）
echo "[smoke] pre-reset rate_limit_qps=null"
curl -fsS -X PATCH "$BASE/api/v1/services/smoke-svc" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"rate_limit_qps":null}' >/dev/null
sleep 0.5  # 让 service:invalidate 传播到 gateway，桶被销毁

echo "[smoke] set service rate_limit_qps=1"
curl -fsS -X PATCH "$BASE/api/v1/services/smoke-svc" \
    -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d '{"rate_limit_qps":1}' >/dev/null
sleep 0.3  # 让新的限流值被 gateway 拉到

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

# rate_limit_qps 的复位由文件顶部的 EXIT trap 统一处理，这里不再显式 reset
echo "[smoke] query call logs"
curl -fsS "$BASE/api/v1/call-logs?limit=5" \
    -H "Authorization: Bearer $TOKEN" | python -m json.tool | head -20

echo "[smoke] verifying audit-events ..."
AUDIT=$(curl -fsS "$BASE/api/v1/audit-events?page_size=10" -H "Authorization: Bearer $TOKEN")
ACTIONS=$(echo "$AUDIT" | python3 -c "import sys,json; print(' '.join(it['action'] for it in json.load(sys.stdin)['items']))")
echo "[smoke]   recent actions: $ACTIONS"
if ! echo "$ACTIONS" | grep -q "service.create"; then
  echo "[smoke] FAIL: 期望审计记录中有 service.create"; exit 1
fi
if ! echo "$ACTIONS" | grep -q "application.create"; then
  echo "[smoke] FAIL: 期望审计记录中有 application.create"; exit 1
fi
if ! echo "$ACTIONS" | grep -q "application.update"; then
  echo "[smoke] FAIL: 期望审计记录中有 application.update（应用驱动授权）"; exit 1
fi

echo "[smoke] OK"
