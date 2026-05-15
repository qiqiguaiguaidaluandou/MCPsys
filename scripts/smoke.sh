#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://localhost:8088}"
USERNAME="${USERNAME:-admin}"
PASSWORD="${PASSWORD:-admin123}"

# 本次跑的窗口起点（UTC ISO，给审计断言 ?from_ts= 用）。在所有 API 调用前抓取。
RUN_SINCE=$(date -u +%Y-%m-%dT%H:%M:%SZ)

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
# 只断言本次跑窗口内必然写入的动作。service.create / application.create 只在
# 首次创建写一次，重跑走 409 幂等路径不写审计 —— 用 ?action=&from_ts=RUN_SINCE
# 锁定到本次跑窗口，避免被历史数据干扰。
check_audit_since() {
    local action="$1"
    local cnt
    cnt=$(curl -fsS "$BASE/api/v1/audit-events?action=$action&from_ts=$RUN_SINCE&page_size=1" \
              -H "Authorization: Bearer $TOKEN" \
              | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
    if [ "$cnt" -lt 1 ]; then
        echo "[smoke] FAIL: 期望本次跑窗口内有审计动作 $action（自 $RUN_SINCE 起 0 条）"
        exit 1
    fi
    echo "[smoke]   audit action '$action' present since run-start (total=$cnt)"
}

check_audit_since "api_key.issue"       # POST /api-keys 每次都写
check_audit_since "application.update"  # PATCH service_ids 每次写两次（清空 + 授权）
check_audit_since "service.update"      # PATCH rate_limit_qps 每次写至少两次

echo "[smoke] stats /overview range=24h"
curl -fsS "$BASE/api/v1/stats/overview?range=24h" -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); \
                  assert d['range']=='24h' and 'calls' in d and 'p95_ms' in d, d" \
    && echo "[smoke]   overview OK"

echo "[smoke] stats /timeseries metric=calls range=1h 应返回 60 个 1m 桶"
curl -fsS "$BASE/api/v1/stats/timeseries?metric=calls&range=1h" -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); n=len(d['points']); \
                  assert n==60, f'expected 60 points, got {n}'; \
                  assert d['bucket']=='1m'" \
    && echo "[smoke]   timeseries OK"

echo "[smoke] stats /breakdown dim=service"
curl -fsS "$BASE/api/v1/stats/breakdown?dim=service&range=24h" -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); \
                  assert d['dim']=='service' and isinstance(d['rows'], list)" \
    && echo "[smoke]   breakdown OK"

echo "[smoke] stats /latency-histogram 应有 7 个桶且末桶 hi=null"
curl -fsS "$BASE/api/v1/stats/latency-histogram?range=24h" -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); \
                  assert len(d['buckets'])==7; assert d['buckets'][-1]['hi'] is None" \
    && echo "[smoke]   latency-histogram OK"

echo "[smoke] stats cache：第二次同样请求应命中 x-cache=hit"
# 不在这里覆盖顶部的 EXIT trap（rate_limit_qps 复位）；用临时变量 + 手动 rm。
HDR_FILE=$(mktemp)
curl -fsS -o /dev/null -D "$HDR_FILE" \
    "$BASE/api/v1/stats/overview?range=1h" -H "Authorization: Bearer $TOKEN"
: > "$HDR_FILE"  # 清空再写第二次的 header
curl -fsS -o /dev/null -D "$HDR_FILE" \
    "$BASE/api/v1/stats/overview?range=1h" -H "Authorization: Bearer $TOKEN"
CACHE=$(tr -d '\r' < "$HDR_FILE" | grep -i '^x-cache:' | awk '{print $2}')
rm -f "$HDR_FILE"
test "$CACHE" = "hit" || { echo "expected x-cache=hit on second call, got '$CACHE'"; exit 1; }
echo "[smoke]   cache x-cache=hit OK"

echo "[smoke] OK"
